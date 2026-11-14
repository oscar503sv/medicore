"""Optional TOTP second factor for superadmins: sign-in step, enrollment and recovery codes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from medicore.application.common.audit import platform_audit_entry
from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import (
    AuthenticationFailed,
    EntityNotFound,
    TooManyLoginAttempts,
    ValidationError,
)
from medicore.application.common.login_throttle import platform_mfa_identifier
from medicore.application.common.platform_mfa import (
    generate_recovery_codes,
    hash_recovery_code,
    looks_like_totp,
)
from medicore.application.common.platform_session import PlatformSessionPolicy
from medicore.application.ports.clock import Clock
from medicore.application.ports.password_hasher import PasswordHasher
from medicore.application.ports.secret_box import SecretBox
from medicore.application.ports.token_issuer import SessionClaims, TokenIssuer
from medicore.application.ports.totp import Totp
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.application.use_cases.platform import (
    PlatformSessionDTO,
    _login_entry,
    _open_platform_session,
)
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.shared.identifiers import PlatformAdminId, SessionId

_audit = platform_audit_entry


def _challenge_expired() -> AuthenticationFailed:
    return AuthenticationFailed(
        "the second-step challenge is missing or expired", code="auth.mfa_challenge_expired"
    )


def _invalid_code() -> AuthenticationFailed:
    return AuthenticationFailed("invalid verification code", code="auth.mfa_invalid")


class _MfaRejected(AuthenticationFailed):
    """A wrong second-step code, carrying why (for the audit trail only)."""

    def __init__(self, reason: str) -> None:
        super().__init__("invalid verification code", code="auth.mfa_invalid")
        self.reason = reason


class CompletePlatformMfaLogin:
    """Second sign-in step: swap a valid challenge + TOTP (or recovery) code for a session."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        tokens: TokenIssuer,
        totp: Totp,
        secret_box: SecretBox,
        clock: Clock,
        policy: PlatformSessionPolicy = PlatformSessionPolicy(),
    ) -> None:
        self._factory = uow_factory
        self._tokens = tokens
        self._totp = totp
        self._box = secret_box
        self._clock = clock
        self._policy = policy

    def execute(
        self,
        challenge_id: SessionId | None,
        code: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PlatformSessionDTO:
        if challenge_id is None:
            raise _challenge_expired()
        now = self._clock.now()
        admin_key = self._challenge_owner(challenge_id, now)
        identifier = platform_mfa_identifier(str(admin_key))
        with self._factory.login_throttle() as throttle:
            locked = throttle.locked_until(identifier, now)
            if locked is not None:
                raise TooManyLoginAttempts(locked, now)
            try:
                session = self._complete(
                    challenge_id, admin_key, code, now, ip_address, user_agent
                )
            except _MfaRejected as exc:
                locked = throttle.record_failure(identifier, now)
                self._audit_failure(
                    challenge_id, admin_key, exc.reason, locked, now, ip_address, user_agent
                )
                raise
            throttle.reset(identifier)
            throttle.purge_stale(now)
            return session

    def _challenge_owner(self, challenge_id: SessionId, now: datetime) -> PlatformAdminId:
        with self._factory.platform_uow() as uow:
            challenge = uow.sessions.get(challenge_id)
        if challenge is None or challenge.scope != "mfa" or not challenge.is_active(now):
            raise _challenge_expired()
        return PlatformAdminId(challenge.user_id)

    def _audit_failure(
        self,
        challenge_id: SessionId,
        admin_id: PlatformAdminId,
        reason: str,
        locked: datetime | None,
        now: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        with self._factory.platform_uow() as uow:
            if locked is not None:
                # Guessing the code any further needs the password again.
                uow.sessions.revoke(challenge_id, now)
            # A lockout is also counted by the monitoring page, like a password lockout.
            action = "auth.platform_login_locked" if locked else "auth.platform_mfa_failed"
            uow.platform_audit.append(
                _login_entry(admin_id, now, action, ip_address, user_agent, reason=reason)
            )
            uow.commit()

    def _complete(
        self,
        challenge_id: SessionId,
        admin_id: PlatformAdminId,
        code: str,
        now: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PlatformSessionDTO:
        failure: AuthenticationFailed | None = None
        with self._factory.platform_uow() as uow:
            challenge = uow.sessions.get(challenge_id)
            if (
                challenge is None
                or challenge.scope != "mfa"
                or challenge.user_id != admin_id.value
                or not challenge.is_active(now)
            ):
                raise _challenge_expired()
            admin = uow.platform_admins.get_by_id(admin_id)
            if admin is None or not admin.is_active:
                failure = AuthenticationFailed(
                    "account is not active", code="auth.account_inactive"
                )
            elif not admin.mfa_enabled:
                failure = _challenge_expired()
            if failure is not None:
                uow.sessions.revoke(challenge_id, now)
                uow.commit()
        if failure is not None:
            raise failure

        with self._factory.platform_uow() as uow:
            admin = uow.platform_admins.get_by_id(admin_id)
            assert admin is not None and admin.mfa_secret is not None
            method = self._verify(uow, admin, code, now)
            # The challenge is spent by its first successful use; losing this race means
            # another request already used it, so no session is opened.
            if not uow.sessions.consume(challenge_id, now):
                raise _challenge_expired()
            admin.last_seen_at = now
            uow.platform_admins.save(admin)
            session_id = _open_platform_session(
                uow, admin, now, self._policy, ip_address, user_agent, mfa=method
            )
            if method == "recovery":
                uow.platform_audit.append(
                    _login_entry(
                        admin.id, now, "auth.platform_mfa_recovery_used", ip_address, user_agent,
                        remaining=uow.platform_recovery_codes.remaining(admin.id),
                    )
                )
            uow.commit()
        token = self._tokens.issue(
            SessionClaims(user_id=str(admin.id), scope="platform", session_id=str(session_id)),
            ttl_minutes=self._policy.lifetime_minutes,
        )
        return PlatformSessionDTO(
            token=token,
            session_id=session_id,
            admin_id=admin.id,
            name=admin.name,
            email=admin.email,
        )

    def _verify(self, uow, admin: PlatformAdmin, code: str, now: datetime) -> str:
        if looks_like_totp(code):
            secret = self._box.open(admin.mfa_secret)
            step = self._totp.matching_step(secret, code, now)
            if step is None:
                raise _MfaRejected("invalid")
            if not admin.accept_totp_step(step):
                raise _MfaRejected("reused")
            return "totp"
        if not uow.platform_recovery_codes.consume(admin.id, hash_recovery_code(code), now):
            raise _MfaRejected("invalid_recovery")
        return "recovery"


# ── Enrollment and management (from the console, authenticated) ────────────────


@dataclass(frozen=True, slots=True)
class MfaEnrollmentDTO:
    secret: str  # base32, shown once so it can be typed into an authenticator app
    otpauth_uri: str


class _MfaManagement:
    """Shared plumbing: password re-check and TOTP check for the self-service operations."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        totp: Totp,
        secret_box: SecretBox,
        clock: Clock,
    ) -> None:
        self._factory = uow_factory
        self._hasher = hasher
        self._totp = totp
        self._box = secret_box
        self._clock = clock

    def _load(self, uow, actor: PlatformActorContext) -> PlatformAdmin:
        admin = uow.platform_admins.get_by_id(actor.admin_id)
        if admin is None:
            raise EntityNotFound("PlatformAdmin", actor.admin_id)
        return admin

    def _check_password(self, admin: PlatformAdmin, password: str) -> None:
        # A 400, not a 401: the admin is authenticated, and a 401 would drop the session.
        if not self._hasher.verify(password, admin.password_hash):
            raise ValidationError(
                "current password is incorrect", code="password.current_incorrect"
            )

    def _authorize(
        self, actor: PlatformActorContext, password: str, code: str, now: datetime
    ) -> int:
        """Password + a fresh TOTP code of an admin who has MFA on; returns the code's time step.

        The code shares the sign-in lockout so a stolen session cannot guess codes without
        limit. The check runs outside any unit of work: a recorded failure must survive the
        error raised right after it.
        """
        with self._factory.platform_uow() as uow:
            admin = self._load(uow, actor)
        self._check_password(admin, password)
        if admin.mfa_secret is None:
            raise ValidationError("MFA is not enabled", code="mfa.not_enabled")
        identifier = platform_mfa_identifier(str(admin.id))
        with self._factory.login_throttle() as throttle:
            locked = throttle.locked_until(identifier, now)
            if locked is not None:
                raise TooManyLoginAttempts(locked, now)
            step = self._totp.matching_step(self._box.open(admin.mfa_secret), code, now)
            replayed = (
                step is not None and admin.mfa_last_step is not None and step <= admin.mfa_last_step
            )
            if step is None or replayed:
                throttle.record_failure(identifier, now)
                raise ValidationError("invalid verification code", code="mfa.invalid_code")
            throttle.reset(identifier)
        return step


class StartPlatformMfaEnrollment(_MfaManagement):
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        totp: Totp,
        secret_box: SecretBox,
        clock: Clock,
        issuer: str,
    ) -> None:
        super().__init__(uow_factory, hasher, totp, secret_box, clock)
        self._issuer = issuer

    def execute(self, actor: PlatformActorContext, password: str) -> MfaEnrollmentDTO:
        with self._factory.platform_uow() as uow:
            admin = self._load(uow, actor)
            self._check_password(admin, password)
            if admin.mfa_enabled:
                raise ValidationError("MFA is already enabled", code="mfa.already_enabled")
            secret = self._totp.new_secret()
            admin.start_mfa_enrollment(self._box.seal(secret))
            uow.platform_admins.save(admin)
            uow.commit()
        return MfaEnrollmentDTO(
            secret=secret,
            otpauth_uri=self._totp.provisioning_uri(secret, admin.email, self._issuer),
        )


class ConfirmPlatformMfaEnrollment(_MfaManagement):
    def execute(self, actor: PlatformActorContext, code: str) -> list[str]:
        """Activate MFA when ``code`` proves the app was set up; returns the recovery codes
        (shown once). The admin's other sessions are closed: they predate the second factor."""
        now = self._clock.now()
        with self._factory.platform_uow() as uow:
            admin = self._load(uow, actor)
            if admin.mfa_enabled:
                raise ValidationError("MFA is already enabled", code="mfa.already_enabled")
            if admin.mfa_pending_secret is None:
                raise ValidationError("MFA enrollment was not started", code="mfa.not_enrolling")
            step = self._totp.matching_step(self._box.open(admin.mfa_pending_secret), code, now)
            if step is None:
                raise ValidationError("invalid verification code", code="mfa.invalid_code")
            admin.confirm_mfa(now, step)
            uow.platform_admins.save(admin)
            codes = generate_recovery_codes()
            uow.platform_recovery_codes.replace_all(
                admin.id, [hash_recovery_code(c) for c in codes], now
            )
            uow.sessions.revoke_all_for_user(admin.id.value, now, except_id=actor.session_id)
            uow.platform_audit.append(
                _audit(actor, now, "auth.platform_mfa_enabled", "PlatformAdmin", str(admin.id))
            )
            uow.commit()
        return codes


class RegeneratePlatformRecoveryCodes(_MfaManagement):
    def execute(self, actor: PlatformActorContext, password: str, code: str) -> list[str]:
        now = self._clock.now()
        step = self._authorize(actor, password, code, now)
        with self._factory.platform_uow() as uow:
            admin = self._load(uow, actor)
            admin.accept_totp_step(step)
            uow.platform_admins.save(admin)
            codes = generate_recovery_codes()
            uow.platform_recovery_codes.replace_all(
                admin.id, [hash_recovery_code(c) for c in codes], now
            )
            uow.platform_audit.append(
                _audit(
                    actor, now, "auth.platform_mfa_recovery_regenerated",
                    "PlatformAdmin", str(admin.id),
                )
            )
            uow.commit()
        return codes


class DisablePlatformMfa(_MfaManagement):
    def execute(self, actor: PlatformActorContext, password: str, code: str) -> None:
        now = self._clock.now()
        self._authorize(actor, password, code, now)
        with self._factory.platform_uow() as uow:
            admin = self._load(uow, actor)
            admin.disable_mfa()
            uow.platform_admins.save(admin)
            uow.platform_recovery_codes.delete_all(admin.id)
            uow.platform_audit.append(
                _audit(actor, now, "auth.platform_mfa_disabled", "PlatformAdmin", str(admin.id))
            )
            uow.commit()


class ResetPlatformAdminMfa:
    """Operator recovery (script): switch MFA off for an admin who lost both factors."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, email: str) -> None:
        now = self._clock.now()
        with self._factory.platform_uow() as uow:
            admin = uow.platform_admins.get_by_email(email)
            if admin is None:
                raise EntityNotFound("PlatformAdmin", email)
            admin.disable_mfa()
            uow.platform_admins.save(admin)
            uow.platform_recovery_codes.delete_all(admin.id)
            uow.sessions.revoke_all_for_user(admin.id.value, now)
            uow.platform_audit.append(
                _login_entry(admin.id, now, "auth.platform_mfa_reset", None, None, source="script")
            )
            uow.commit()
