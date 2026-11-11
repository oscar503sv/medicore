"""Every use case that sets a password applies the policy."""

from __future__ import annotations

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.auth import ChangePassword
from medicore.application.use_cases.platform import ResetUserPassword as PlatformReset
from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    ResetUserPassword,
    ResetUserPasswordCommand,
)
from medicore.domain.enums import Role
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FixedClock, PlainPasswordHasher


def _code(call) -> str:
    with pytest.raises(ValidationError) as exc:
        call()
    return exc.value.code


def _change(seed, new: str, current: str = PASSWORD):
    return ChangePassword(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
        seed.doctor_actor, current, new
    )


class TestChangePassword:
    def test_accepts_a_strong_password(self):
        seed = seed_clinic()
        _change(seed, "Rio-Lempa-482")
        stored = seed.factory.store.users[seed.doctor.id.value]
        assert PlainPasswordHasher().verify("Rio-Lempa-482", stored.password_hash)

    def test_rejects_a_weak_one(self):
        seed = seed_clinic()
        assert _code(lambda: _change(seed, "corta1")) == "password.too_short"
        assert _code(lambda: _change(seed, "Clinica2024!")) == "password.common"

    def test_rejects_the_users_own_name_or_clinic(self):
        seed = seed_clinic()  # the doctor is "Dra. Elena Ruiz" at clinica-norte
        assert _code(lambda: _change(seed, "elena-2024#x")) == "password.personal"
        assert _code(lambda: _change(seed, "Mi-norte-2024")) == "password.personal"

    def test_new_must_differ_from_current(self):
        seed = seed_clinic()
        _change(seed, "Rio-Lempa-482")
        assert (
            _code(lambda: _change(seed, "Rio-Lempa-482", current="Rio-Lempa-482"))
            == "password.same_as_current"
        )

    def test_wrong_current_password_is_checked_first(self):
        seed = seed_clinic()
        assert _code(lambda: _change(seed, "corta", current="nope")) == "password.current_incorrect"


class TestTemporaryPasswords:
    def test_invite_applies_the_policy(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        use_case = InviteUser(uow, PlainPasswordHasher(), FixedClock())

        def invite(password):
            return use_case.execute(
                seed.actor(seed.admin),
                InviteUserCommand(
                    name="Mario Rivas", email="mario@n.test", role=Role.NURSE, password=password
                ),
            )

        assert _code(lambda: invite("mario-2024!x")) == "password.personal"
        assert invite("Rio-Lempa-482").must_change_password

    def test_clinic_reset_applies_the_policy(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        cmd = ResetUserPasswordCommand(user_id=seed.nurse.id, password="password123")
        use_case = ResetUserPassword(uow, PlainPasswordHasher(), FixedClock())
        assert _code(lambda: use_case.execute(seed.actor(seed.admin), cmd)) == "password.common"

    def test_console_reset_applies_the_policy(self):
        seed = seed_clinic()
        actor = PlatformActorContext(admin_id=seed.platform_admin.id)
        use_case = PlatformReset(seed.factory, PlainPasswordHasher(), FixedClock())
        assert (
            _code(lambda: use_case.execute(actor, seed.tenant.id, seed.nurse.id, "aaaaaaaaaa"))
            == "password.too_simple"
        )
