"""Optional superadmin MFA: sign-in step, enrollment, recovery codes, reset."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import (
    AuthenticationFailed,
    TooManyLoginAttempts,
    ValidationError,
)
from medicore.application.common.platform_mfa import (
    RECOVERY_CODE_COUNT,
    generate_recovery_codes,
    hash_recovery_code,
    looks_like_totp,
    mfa_required_for,
)
from medicore.application.common.platform_session import PlatformSessionPolicy
from medicore.application.use_cases.platform import (
    AuthenticatePlatformAdmin,
    GetPlatformAdmin,
    PlatformMfaChallengeDTO,
    PlatformSessionDTO,
)
from medicore.application.use_cases.platform_mfa import (
    CompletePlatformMfaLogin,
    ConfirmPlatformMfaEnrollment,
    DisablePlatformMfa,
    RegeneratePlatformRecoveryCodes,
    ResetPlatformAdminMfa,
    StartPlatformMfaEnrollment,
)
from medicore.domain.enums import UserStatus
from medicore.domain.shared.identifiers import SessionId
from medicore.infrastructure.auth.totp import Rfc6238Totp
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher, PlainSecretBox

START = datetime(2026, 11, 14, 9, 0)
POLICY = PlatformSessionPolicy()


class World:
    """One seeded clinic plus every collaborator, wired with the real TOTP adapter."""

    def __init__(self) -> None:
        self.seed = seed_clinic()
        self.factory = self.seed.factory
        self.clock = FixedClock(START)
        self.hasher = PlainPasswordHasher()
        self.issuer = FakeTokenIssuer()
        self.totp = Rfc6238Totp()
        self.box = PlainSecretBox()
        self.admin = self.seed.platform_admin
        self.actor = PlatformActorContext(admin_id=self.admin.id)

    def login(self):
        return AuthenticatePlatformAdmin(
            self.factory, self.hasher, self.issuer, self.clock, POLICY
        ).execute(self.admin.email, PASSWORD)

    def verify(self, challenge, code):
        return CompletePlatformMfaLogin(
            self.factory, self.issuer, self.totp, self.box, self.clock, POLICY
        ).execute(_challenge_id(challenge), code)

    def _mgmt(self, cls, *extra):
        return cls(self.factory, self.hasher, self.totp, self.box, self.clock, *extra)

    def enroll(self) -> tuple[str, list[str]]:
        """Run the whole enrollment; returns the base32 secret and the recovery codes."""
        dto = self._mgmt(StartPlatformMfaEnrollment, "Medicore").execute(self.actor, PASSWORD)
        codes = self._mgmt(ConfirmPlatformMfaEnrollment).execute(
            self.actor, self.totp.code_at(dto.secret, self.clock.now())
        )
        return dto.secret, codes

    def code(self, secret: str) -> str:
        return self.totp.code_at(secret, self.clock.now())

    def next_period(self) -> None:
        self.clock.set(self.clock.now() + timedelta(seconds=31))

    def audit_actions(self) -> list[str]:
        return [e.action for e in self.factory.store.platform_audit.values()]

    def stored_admin(self):
        return self.factory.store.platform_admins[self.admin.id.value]


def _challenge_id(challenge: PlatformMfaChallengeDTO) -> SessionId:
    return SessionId.parse(FakeTokenIssuer().decode(challenge.token).session_id)


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def mfa_world(world) -> World:
    world.secret, world.recovery = world.enroll()
    world.next_period()
    return world


# ── Sign-in ──────────────────────────────────────────────────────────────────


def test_login_without_mfa_opens_the_session_as_before(world):
    assert isinstance(world.login(), PlatformSessionDTO)


def test_login_with_mfa_returns_only_a_challenge(mfa_world):
    world = mfa_world
    result = world.login()
    assert isinstance(result, PlatformMfaChallengeDTO)
    assert result.expires_in == 300
    assert world.issuer.decode(result.token).scope == "mfa"
    sessions = world.factory.store.sessions.values()
    challenge = next(s for s in sessions if s.scope == "mfa")
    assert challenge.expires_at == world.clock.now() + timedelta(minutes=5)
    assert not any(s.scope == "platform" and s.created_at == world.clock.now() for s in sessions)
    assert "auth.platform_login" not in world.audit_actions()


def test_valid_code_completes_the_login(mfa_world):
    world = mfa_world
    challenge = world.login()
    session = world.verify(challenge, world.code(world.secret))
    assert isinstance(session, PlatformSessionDTO)
    stored = world.factory.store.sessions[session.session_id.value]
    assert stored.scope == "platform" and stored.last_activity_at == world.clock.now()
    login = next(
        e for e in world.factory.store.platform_audit.values() if e.action == "auth.platform_login"
    )
    assert login.metadata == {"mfa": "totp"}


def test_wrong_code_is_rejected_and_audited(mfa_world):
    world = mfa_world
    challenge = world.login()
    with pytest.raises(AuthenticationFailed) as exc:
        world.verify(challenge, "000000")
    assert exc.value.code == "auth.mfa_invalid"
    failed = [
        e for e in world.factory.store.platform_audit.values()
        if e.action == "auth.platform_mfa_failed"
    ]
    assert [e.metadata for e in failed] == [{"reason": "invalid"}]


def test_a_code_cannot_be_used_twice(mfa_world):
    world = mfa_world
    code = world.code(world.secret)
    world.verify(world.login(), code)
    with pytest.raises(AuthenticationFailed):
        world.verify(world.login(), code)
    reasons = [
        e.metadata["reason"] for e in world.factory.store.platform_audit.values()
        if e.action == "auth.platform_mfa_failed"
    ]
    assert reasons == ["reused"]


def test_the_code_used_to_enroll_cannot_be_replayed_at_login():
    world = World()
    secret, _ = world.enroll()  # same period: the confirmation code is spent
    challenge = world.login()
    with pytest.raises(AuthenticationFailed):
        world.verify(challenge, world.code(secret))


def test_challenge_is_single_use(mfa_world):
    world = mfa_world
    challenge = world.login()
    world.verify(challenge, world.code(world.secret))
    world.next_period()
    with pytest.raises(AuthenticationFailed) as exc:
        world.verify(challenge, world.code(world.secret))
    assert exc.value.code == "auth.mfa_challenge_expired"


def test_expired_challenge_is_rejected(mfa_world):
    world = mfa_world
    challenge = world.login()
    world.clock.set(world.clock.now() + timedelta(minutes=5, seconds=1))
    with pytest.raises(AuthenticationFailed) as exc:
        world.verify(challenge, world.code(world.secret))
    assert exc.value.code == "auth.mfa_challenge_expired"


def test_missing_challenge_is_rejected(mfa_world):
    with pytest.raises(AuthenticationFailed) as exc:
        CompletePlatformMfaLogin(
            mfa_world.factory, mfa_world.issuer, mfa_world.totp, mfa_world.box, mfa_world.clock
        ).execute(None, "123456")
    assert exc.value.code == "auth.mfa_challenge_expired"


def test_a_session_row_is_not_a_challenge(mfa_world):
    other = World()
    dto = other.login()  # a platform session id handed in as a challenge must not verify
    with pytest.raises(AuthenticationFailed) as exc:
        CompletePlatformMfaLogin(
            other.factory, other.issuer, other.totp, other.box, other.clock
        ).execute(dto.session_id, "123456")
    assert exc.value.code == "auth.mfa_challenge_expired"


def test_lockout_after_five_failures_revokes_the_challenge(mfa_world):
    world = mfa_world
    challenge = world.login()
    for _ in range(4):
        with pytest.raises(AuthenticationFailed):
            world.verify(challenge, "000000")
    with pytest.raises(AuthenticationFailed):
        world.verify(challenge, "000000")  # the 5th engages the lockout
    stored = world.factory.store.sessions[_challenge_id(challenge).value]
    assert stored.revoked_at is not None
    with pytest.raises(AuthenticationFailed) as exc:
        world.verify(challenge, world.code(world.secret))
    assert exc.value.code == "auth.mfa_challenge_expired"
    assert "auth.platform_login_locked" in world.audit_actions()
    with pytest.raises(TooManyLoginAttempts):  # a fresh challenge is locked out as well
        world.verify(world.login(), world.code(world.secret))


def test_lockout_does_not_depend_on_which_challenge_is_used(mfa_world):
    world = mfa_world
    for _ in range(5):
        with pytest.raises(AuthenticationFailed):
            world.verify(world.login(), "000000")
    with pytest.raises(TooManyLoginAttempts):
        world.verify(world.login(), world.code(world.secret))


def test_successful_verification_resets_the_failure_count(mfa_world):
    world = mfa_world
    for _ in range(3):
        with pytest.raises(AuthenticationFailed):
            world.verify(world.login(), "000000")
    world.verify(world.login(), world.code(world.secret))
    world.next_period()
    for _ in range(4):
        with pytest.raises(AuthenticationFailed):
            world.verify(world.login(), "000000")
    world.verify(world.login(), world.code(world.secret))  # not locked: the count restarted


def test_recovery_code_works_once(mfa_world):
    world = mfa_world
    code = world.recovery[0]
    session = world.verify(world.login(), code.upper())  # case and dash are forgiven
    assert isinstance(session, PlatformSessionDTO)
    audit = {e.action: e.metadata for e in world.factory.store.platform_audit.values()}
    assert audit["auth.platform_mfa_recovery_used"] == {"remaining": RECOVERY_CODE_COUNT - 1}
    assert audit["auth.platform_login"] == {"mfa": "recovery"}
    with pytest.raises(AuthenticationFailed):
        world.verify(world.login(), code)
    reasons = [
        e.metadata["reason"] for e in world.factory.store.platform_audit.values()
        if e.action == "auth.platform_mfa_failed"
    ]
    assert reasons == ["invalid_recovery"]


def test_inactive_admin_cannot_finish_the_login(mfa_world):
    world = mfa_world
    challenge = world.login()
    world.stored_admin().status = UserStatus.SUSPENDED
    with pytest.raises(AuthenticationFailed) as exc:
        world.verify(challenge, world.code(world.secret))
    assert exc.value.code == "auth.account_inactive"
    assert world.factory.store.sessions[_challenge_id(challenge).value].revoked_at is not None


def test_disabling_mfa_meanwhile_kills_the_pending_challenge(mfa_world):
    world = mfa_world
    challenge = world.login()
    world.stored_admin().disable_mfa()
    with pytest.raises(AuthenticationFailed) as exc:
        world.verify(challenge, world.code(world.secret))
    assert exc.value.code == "auth.mfa_challenge_expired"


# ── Enrollment ───────────────────────────────────────────────────────────────


def test_full_enrollment(world):
    secret, codes = world.enroll()
    admin = world.stored_admin()
    assert admin.mfa_enabled and admin.mfa_pending_secret is None
    assert admin.mfa_secret == PlainSecretBox.PREFIX + secret  # stored sealed, not in clear
    assert len(codes) == RECOVERY_CODE_COUNT and len(set(codes)) == RECOVERY_CODE_COUNT
    store = world.factory.store.platform_recovery_codes[admin.id.value]
    assert set(store) == {hash_recovery_code(c) for c in codes}
    assert "auth.platform_mfa_enabled" in world.audit_actions()
    profile = GetPlatformAdmin(world.factory).execute(world.actor)
    assert profile.recovery_codes_remaining == RECOVERY_CODE_COUNT


def test_setup_needs_the_current_password(world):
    with pytest.raises(ValidationError) as exc:
        world._mgmt(StartPlatformMfaEnrollment, "Medicore").execute(world.actor, "wrong")
    assert exc.value.code == "password.current_incorrect"
    assert world.stored_admin().mfa_pending_secret is None


def test_setup_is_refused_when_already_enabled(mfa_world):
    with pytest.raises(ValidationError) as exc:
        mfa_world._mgmt(StartPlatformMfaEnrollment, "Medicore").execute(
            mfa_world.actor, PASSWORD
        )
    assert exc.value.code == "mfa.already_enabled"


def test_setup_returns_the_uri_with_the_issuer(world):
    dto = world._mgmt(StartPlatformMfaEnrollment, "Medicore").execute(world.actor, PASSWORD)
    assert dto.otpauth_uri.startswith("otpauth://totp/Medicore:")
    assert f"secret={dto.secret}" in dto.otpauth_uri


def test_confirm_with_a_wrong_code_changes_nothing(world):
    world._mgmt(StartPlatformMfaEnrollment, "Medicore").execute(world.actor, PASSWORD)
    with pytest.raises(ValidationError) as exc:
        world._mgmt(ConfirmPlatformMfaEnrollment).execute(world.actor, "000000")
    assert exc.value.code == "mfa.invalid_code"
    assert not world.stored_admin().mfa_enabled


def test_confirm_without_setup_is_refused(world):
    with pytest.raises(ValidationError) as exc:
        world._mgmt(ConfirmPlatformMfaEnrollment).execute(world.actor, "123456")
    assert exc.value.code == "mfa.not_enrolling"


def test_confirm_closes_the_other_sessions_but_not_the_current_one(world):
    current = world.login()
    other = world.login()
    actor = PlatformActorContext(admin_id=world.admin.id, session_id=current.session_id)
    dto = world._mgmt(StartPlatformMfaEnrollment, "Medicore").execute(actor, PASSWORD)
    world._mgmt(ConfirmPlatformMfaEnrollment).execute(actor, world.code(dto.secret))
    sessions = world.factory.store.sessions
    assert sessions[current.session_id.value].revoked_at is None
    assert sessions[other.session_id.value].revoked_at is not None


# ── Management ───────────────────────────────────────────────────────────────


def test_regenerate_replaces_the_codes(mfa_world):
    world = mfa_world
    old = world.recovery[0]
    new = world._mgmt(RegeneratePlatformRecoveryCodes).execute(
        world.actor, PASSWORD, world.code(world.secret)
    )
    assert len(new) == RECOVERY_CODE_COUNT and not set(new) & set(world.recovery)
    assert "auth.platform_mfa_recovery_regenerated" in world.audit_actions()
    with pytest.raises(AuthenticationFailed):
        world.verify(world.login(), old)
    world.verify(world.login(), new[0])


def test_regenerate_needs_password_and_code(mfa_world):
    world = mfa_world
    with pytest.raises(ValidationError) as exc:
        world._mgmt(RegeneratePlatformRecoveryCodes).execute(
            world.actor, "wrong", world.code(world.secret)
        )
    assert exc.value.code == "password.current_incorrect"
    with pytest.raises(ValidationError) as exc:
        world._mgmt(RegeneratePlatformRecoveryCodes).execute(world.actor, PASSWORD, "000000")
    assert exc.value.code == "mfa.invalid_code"
    assert hash_recovery_code(world.recovery[0]) in (
        world.factory.store.platform_recovery_codes[world.admin.id.value]
    )


def test_regenerate_and_disable_are_refused_without_mfa(world):
    for cls in (RegeneratePlatformRecoveryCodes, DisablePlatformMfa):
        with pytest.raises(ValidationError) as exc:
            world._mgmt(cls).execute(world.actor, PASSWORD, "123456")
        assert exc.value.code == "mfa.not_enabled"


def test_guessing_codes_through_management_is_throttled(mfa_world):
    world = mfa_world
    for _ in range(5):
        with pytest.raises(ValidationError):
            world._mgmt(DisablePlatformMfa).execute(world.actor, PASSWORD, "000000")
    with pytest.raises(TooManyLoginAttempts):
        world._mgmt(DisablePlatformMfa).execute(world.actor, PASSWORD, world.code(world.secret))


def test_disable_turns_mfa_off(mfa_world):
    world = mfa_world
    world._mgmt(DisablePlatformMfa).execute(world.actor, PASSWORD, world.code(world.secret))
    admin = world.stored_admin()
    assert not admin.mfa_enabled
    assert world.admin.id.value not in world.factory.store.platform_recovery_codes
    assert "auth.platform_mfa_disabled" in world.audit_actions()
    assert isinstance(world.login(), PlatformSessionDTO)


def test_script_reset_clears_mfa_codes_and_sessions(mfa_world):
    world = mfa_world
    session = world.verify(world.login(), world.code(world.secret))
    ResetPlatformAdminMfa(world.factory, world.clock).execute(world.admin.email)
    assert not world.stored_admin().mfa_enabled
    assert world.admin.id.value not in world.factory.store.platform_recovery_codes
    assert world.factory.store.sessions[session.session_id.value].revoked_at is not None
    assert "auth.platform_mfa_reset" in world.audit_actions()


def test_script_reset_of_unknown_email_fails(world):
    from medicore.application.common.errors import EntityNotFound

    with pytest.raises(EntityNotFound):
        ResetPlatformAdminMfa(world.factory, world.clock).execute("nobody@medicore.test")


# ── Helpers and extension point ──────────────────────────────────────────────


def test_mfa_required_follows_the_admin_unless_enforced(mfa_world):
    off = World().admin
    assert mfa_required_for(off) is False
    assert mfa_required_for(off, enforced=True) is True
    assert mfa_required_for(mfa_world.stored_admin()) is True


def test_recovery_codes_have_the_expected_shape():
    codes = generate_recovery_codes()
    assert len(codes) == RECOVERY_CODE_COUNT == len(set(codes))
    for code in codes:
        first, dash, second = code.partition("-")
        assert (len(first), dash, len(second)) == (5, "-", 5)
        assert code == code.lower()


def test_recovery_hash_ignores_case_dashes_and_spaces():
    assert hash_recovery_code("ABCDE-fghij") == hash_recovery_code(" abcde fghij ")
    assert len(hash_recovery_code("abcde-fghij")) == 64


def test_totp_and_recovery_codes_are_told_apart():
    assert looks_like_totp("123456") and looks_like_totp("123 456")
    assert not looks_like_totp("abcde-fghij") and not looks_like_totp("12345")
