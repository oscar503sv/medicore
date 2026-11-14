"""FastAPI dependency providers.

All database-backed operations go through a UnitOfWork scoped to the authenticated
tenant. Read-only handlers use ``with uow:`` without calling ``commit()`` so the
session is rolled back (noop) and closed cleanly when the block exits.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request, status

from medicore.application.common.access import ensure_may_sign_in
from medicore.application.common.context import ActorContext, PlatformActorContext
from medicore.application.common.entitlements import ensure_writable, granted_permissions
from medicore.application.common.timezone import tenant_today
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import PlatformAdminId, SessionId, TenantId, UserId
from medicore.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from medicore.infrastructure.auth.code_generator import DbSequentialCodeGenerator
from medicore.infrastructure.auth.jwt_token_issuer import JwtTokenIssuer
from medicore.infrastructure.auth.system_clock import SystemClock
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.engine import get_session_factory
from medicore.infrastructure.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
    SqlAlchemyUnitOfWorkFactory,
)
from medicore.infrastructure.runtime import ProcessRuntimeInfo
from medicore.presentation.client_ip import resolve_client_ip
from medicore.presentation.cookies import (
    CSRF_COOKIE,
    CSRF_HEADER,
    PLATFORM_COOKIE,
    SESSION_COOKIE,
    is_mutating,
)
from medicore.presentation.errors import ApiError

# ── Singletons (cheap to construct, no shared mutable state) ──────────────────

def get_jwt_issuer() -> JwtTokenIssuer:
    return JwtTokenIssuer()


def get_hasher() -> BcryptPasswordHasher:
    return BcryptPasswordHasher()


def get_clock() -> SystemClock:
    return SystemClock()


def get_uow_factory() -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory(get_session_factory())


def get_runtime() -> ProcessRuntimeInfo:
    return ProcessRuntimeInfo()


# ── Authentication ─────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str | None:
    """Client IP for audit trails: ``X-Forwarded-For`` is honored only when the request
    comes through a proxy listed in ``TRUSTED_PROXIES`` (else it is spoofable noise and
    the socket peer is used)."""
    return resolve_client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        get_settings().trusted_proxy_networks,
    )


def _session_token(request: Request, authorization: str | None, cookie_name: str) -> str:
    """Resolve the session token: Bearer header first, session cookie as fallback.

    Cookie-authenticated mutations must pass the double-submit CSRF check — the browser
    attaches cookies automatically, so we require a header a cross-site page cannot set.
    Bearer requests skip it: the header itself is never sent automatically.
    """
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()

    token = request.cookies.get(cookie_name)
    if not token:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid Authorization header",
            code="auth.not_authenticated",
        )
    if is_mutating(request.method):
        csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
        csrf_header = request.headers.get(CSRF_HEADER, "")
        if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
            raise ApiError(
                status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid", code="auth.csrf_invalid"
            )
    return token


def _session_id_or_401(claims) -> SessionId:
    """Extract the ``sid`` claim; tokens without one (or malformed) are rejected."""
    if not claims.session_id:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Session revoked or expired", code="auth.session_expired"
        )
    try:
        return SessionId.parse(claims.session_id)
    except InvalidValueObject as exc:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Session revoked or expired", code="auth.session_expired"
        ) from exc


def revoke_session_token(token: str | None, issuer: JwtTokenIssuer, factory, now) -> None:
    """Best-effort server-side revocation on logout: an invalid or expired token simply
    has nothing left to revoke, so it never raises."""
    if not token:
        return
    try:
        claims = issuer.decode(token)
        if not claims.session_id:
            return
        session_id = SessionId.parse(claims.session_id)
        if claims.scope == "platform":
            with factory.platform_uow() as uow:
                uow.sessions.revoke(session_id, now)
                uow.commit()
        elif claims.tenant_id:
            with factory.for_tenant(TenantId.parse(claims.tenant_id)) as uow:
                uow.sessions.revoke(session_id, now)
                uow.commit()
    except (jwt.InvalidTokenError, InvalidValueObject):
        return


def _decode_or_401(issuer: JwtTokenIssuer, token: str):
    try:
        return issuer.decode(token)
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Token expired", code="auth.session_expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Invalid token", code="auth.session_expired"
        ) from exc


# Still allowed when the clinic is read-only: signing out, changing one's password or
# preferences, and marking notifications as read never touch clinical data.
_WRITABLE_WHEN_READ_ONLY = ("/api/v1/auth/", "/api/v1/notifications")


def _always_writable(path: str) -> bool:
    return path.startswith(_WRITABLE_WHEN_READ_ONLY)


def get_actor(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    issuer: JwtTokenIssuer = Depends(get_jwt_issuer),
    factory: SqlAlchemyUnitOfWorkFactory = Depends(get_uow_factory),
    clock: SystemClock = Depends(get_clock),
) -> ActorContext:
    """Authenticate the request (Bearer header or mc_session cookie) and return the actor.

    Resolves the tenant's role-permission override so every permission check in the
    request honors the clinic's customization, and requires the token's server-side
    session (``sid``) to still be alive — a revoked session means 401 immediately, no
    matter how long the JWT itself remains valid. The clinic and the account must still be
    allowed to hold a session (the access policy), else 401. Raises 401 if no valid credential is
    present, 403 if a cookie-authenticated mutation fails the CSRF check.
    """
    token = _session_token(request, authorization, SESSION_COOKIE)
    claims = _decode_or_401(issuer, token)

    if claims.scope != "tenant" or not claims.tenant_id:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Not a tenant session", code="auth.wrong_session"
        )

    session_id = _session_id_or_401(claims)
    tenant_id = TenantId.parse(claims.tenant_id)
    with factory.for_tenant(tenant_id) as uow:
        session = uow.sessions.get(session_id)
        tenant = uow.tenants.get_by_id(tenant_id)
        user = uow.users.get_by_id(UserId.parse(claims.user_id))
        effective = granted_permissions(uow, tenant, user) if tenant and user else frozenset()
    if session is None or tenant is None or user is None or not session.is_active(clock.now()):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Session revoked or expired", code="auth.session_expired"
        )
    # Suspending or archiving a clinic (or an account) revokes its sessions; this keeps any
    # that slipped through from working, on every request.
    ensure_may_sign_in(tenant, user, support=session.impersonator_id is not None)
    if is_mutating(request.method) and not _always_writable(request.url.path):
        ensure_writable(tenant, tenant_today(tenant, clock))

    return ActorContext(
        user_id=user.id,
        tenant_id=tenant_id,
        # The stored role, not the token's: a role change applies on the next request,
        # consistent with the permissions resolved above.
        role=user.role,
        impersonated_by=(
            PlatformAdminId.parse(claims.impersonator) if claims.impersonator else None
        ),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        permissions=frozenset(str(p) for p in effective),
        session_id=session_id,
    )


def get_platform_actor(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    issuer: JwtTokenIssuer = Depends(get_jwt_issuer),
    factory: SqlAlchemyUnitOfWorkFactory = Depends(get_uow_factory),
    clock: SystemClock = Depends(get_clock),
) -> PlatformActorContext:
    """Authenticate the platform superadmin (Bearer header or mc_platform cookie).

    Raises 401 if no valid credential is present, the token is not a platform session,
    or its server-side session has been revoked; 403 if a cookie-authenticated mutation
    fails the CSRF check.
    """
    token = _session_token(request, authorization, PLATFORM_COOKIE)
    claims = _decode_or_401(issuer, token)

    if claims.scope != "platform":
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Not a platform session", code="auth.wrong_session"
        )

    session_id = _session_id_or_401(claims)
    with factory.platform_uow() as uow:
        session = uow.sessions.get(session_id)
    if session is None or not session.is_active(clock.now()):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "Session revoked or expired", code="auth.session_expired"
        )

    return PlatformActorContext(
        admin_id=PlatformAdminId.parse(claims.user_id),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


# ── Convenience per-request UoW ───────────────────────────────────────────────

def get_uow(
    actor: ActorContext = Depends(get_actor),
    factory: SqlAlchemyUnitOfWorkFactory = Depends(get_uow_factory),
) -> Iterator[SqlAlchemyUnitOfWork]:
    """Yield a tenant-scoped UoW for the current request and always close its session.

    Handlers still use ``with uow:`` to delimit transactions (commit/rollback); the
    ``finally`` here guarantees the underlying connection is returned to the pool even
    for read-only handlers that don't open a ``with`` block or that read again after a
    write use case has exited its own ``with``. ``Session.close()`` is idempotent, so the
    double close (here + in a ``with`` block) is harmless.
    """
    uow = factory.for_tenant(actor.tenant_id)
    try:
        yield uow
    finally:
        uow._session.close()


def get_codes(uow: SqlAlchemyUnitOfWork = Depends(get_uow)) -> DbSequentialCodeGenerator:
    """Code generator sharing the request's session so its counter increments
    are part of the same transaction."""
    return DbSequentialCodeGenerator(uow._session, uow.tenant_id.value)


# Type aliases for annotated injection
Actor = Annotated[ActorContext, Depends(get_actor)]
PlatformActor = Annotated[PlatformActorContext, Depends(get_platform_actor)]
UoW = Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)]
Clock = Annotated[SystemClock, Depends(get_clock)]
Codes = Annotated[DbSequentialCodeGenerator, Depends(get_codes)]
UoWFactory = Annotated[SqlAlchemyUnitOfWorkFactory, Depends(get_uow_factory)]
Hasher = Annotated[BcryptPasswordHasher, Depends(get_hasher)]
JwtIssuer = Annotated[JwtTokenIssuer, Depends(get_jwt_issuer)]
Runtime = Annotated[ProcessRuntimeInfo, Depends(get_runtime)]
