"""FastAPI dependency providers.

All database-backed operations go through a UnitOfWork scoped to the authenticated
tenant. Read-only handlers use ``with uow:`` without calling ``commit()`` so the
session is rolled back (noop) and closed cleanly when the block exits.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from medicore.application.common.context import ActorContext, PlatformActorContext
from medicore.application.common.permissions import effective_permissions
from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import PlatformAdminId, TenantId, UserId
from medicore.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from medicore.infrastructure.auth.code_generator import DbSequentialCodeGenerator
from medicore.infrastructure.auth.jwt_token_issuer import JwtTokenIssuer
from medicore.infrastructure.auth.system_clock import SystemClock
from medicore.infrastructure.database.engine import get_session_factory
from medicore.infrastructure.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
    SqlAlchemyUnitOfWorkFactory,
)

# ── Singletons (cheap to construct, no shared mutable state) ──────────────────

def get_jwt_issuer() -> JwtTokenIssuer:
    return JwtTokenIssuer()


def get_hasher() -> BcryptPasswordHasher:
    return BcryptPasswordHasher()


def get_clock() -> SystemClock:
    return SystemClock()


def get_uow_factory() -> SqlAlchemyUnitOfWorkFactory:
    return SqlAlchemyUnitOfWorkFactory(get_session_factory())


# ── Authentication ─────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str | None:
    """Best-effort client IP: first ``X-Forwarded-For`` hop, else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip() if forwarded else ""
    if first:
        return first
    return request.client.host if request.client else None


def get_actor(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    issuer: JwtTokenIssuer = Depends(get_jwt_issuer),
    factory: SqlAlchemyUnitOfWorkFactory = Depends(get_uow_factory),
) -> ActorContext:
    """Decode the Bearer token and return the authenticated actor.

    Resolves the tenant's role-permission override so every permission check in the
    request honors the clinic's customization. Raises 401 if the header is missing,
    malformed or expired.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = issuer.decode(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    if claims.scope != "tenant" or not claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a tenant session"
        )

    tenant_id = TenantId.parse(claims.tenant_id)
    role = Role(claims.role)
    with factory.for_tenant(tenant_id) as uow:
        override = uow.role_permissions.get_by_role(role)
    effective = effective_permissions(role, override.permissions if override else None)

    return ActorContext(
        user_id=UserId.parse(claims.user_id),
        tenant_id=tenant_id,
        role=role,
        impersonated_by=(
            PlatformAdminId.parse(claims.impersonator) if claims.impersonator else None
        ),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        permissions=frozenset(str(p) for p in effective),
    )


def get_platform_actor(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    issuer: JwtTokenIssuer = Depends(get_jwt_issuer),
) -> PlatformActorContext:
    """Decode the Bearer token and return the authenticated platform superadmin.

    Raises 401 if the header is missing/expired/invalid or the token is not a platform session.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = issuer.decode(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    if claims.scope != "platform":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a platform session"
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
