"""Per-request validation of a superadmin console session."""

from __future__ import annotations

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import AuthenticationFailed
from medicore.application.common.platform_session import PlatformSessionPolicy
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import PlatformAdminId, SessionId


def _expired() -> AuthenticationFailed:
    return AuthenticationFailed("session revoked or expired", code="auth.session_expired")


class ResolvePlatformSession:
    """Check that a console session is alive, not idle and still owned by an active admin,
    and record its activity (throttled)."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        policy: PlatformSessionPolicy = PlatformSessionPolicy(),
    ) -> None:
        self._factory = uow_factory
        self._clock = clock
        self._policy = policy

    def execute(
        self,
        admin_id: str,
        session_id: SessionId,
        *,
        background: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PlatformActorContext:
        # ``background`` requests (polling) must not keep an abandoned console alive.
        try:
            admin_key = PlatformAdminId.parse(admin_id)
        except InvalidValueObject as exc:
            raise _expired() from exc
        now = self._clock.now()
        # The revocations below must outlive the rejection, so the error is raised only
        # after the transaction that committed them has closed.
        failure: AuthenticationFailed | None = None
        with self._factory.platform_uow() as uow:
            session = uow.sessions.get(session_id)
            if (
                session is None
                or session.scope != "platform"
                or session.user_id != admin_key.value
                or not session.is_active(now)
            ):
                raise _expired()
            admin = uow.platform_admins.get_by_id(admin_key)
            if session.is_idle(now, self._policy.idle):
                failure = AuthenticationFailed(
                    "session closed by inactivity", code="auth.session_idle_timeout"
                )
            elif admin is None or not admin.is_active:
                failure = AuthenticationFailed(
                    "account is not active", code="auth.account_inactive"
                )
            if failure is not None:
                uow.sessions.revoke(session_id, now)
                uow.commit()
            else:
                if not background and session.needs_touch(now, self._policy.touch_every):
                    uow.sessions.touch(session_id, now)
                    uow.commit()
        if failure is not None:
            raise failure
        return PlatformActorContext(
            admin_id=admin_key,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
        )
