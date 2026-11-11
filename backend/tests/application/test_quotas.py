"""Use-case tests: subscription quotas on users (doctors / support staff) and sites."""

from __future__ import annotations

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.use_cases.organization import AddLocation
from medicore.application.use_cases.platform import UnlockUser, UpdateTenantUser
from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    ReactivateUser,
    SuspendUser,
    UpdateUser,
    UpdateUserRole,
)
from medicore.domain.enums import Role
from medicore.domain.services.plan_catalog import CLINICA, INDEPENDIENTE
from medicore.domain.shared.errors import QuotaExceeded
from medicore.domain.value_objects.plan_limits import LimitOverrides
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, PlainPasswordHasher

# The seed clinic has an admin (free), one doctor, one nurse and one receptionist:
# 1 doctor and 2 support seats in use.


def on_plan(seed, plan_code: str, overrides: LimitOverrides | None = None):
    uow = seed.factory.for_tenant(seed.tenant.id)
    tenant = uow.tenants.get_by_id(seed.tenant.id)
    tenant.subscription = Subscription(plan_code=plan_code, limit_overrides=overrides)
    uow.tenants.save(tenant)
    return uow


def invite(seed, uow, role: Role, n: int = 0):
    return InviteUser(uow, PlainPasswordHasher(), FixedClock()).execute(
        seed.actor(seed.admin),
        InviteUserCommand(
            name=f"Nuevo {n}", email=f"nuevo{n}-{role}@norte.test", role=role,
            password="temp-pass-123",
        ),
    )


class TestInvite:
    def test_doctors_up_to_the_limit(self):
        seed = seed_clinic()
        uow = on_plan(seed, CLINICA)  # 3 doctors
        invite(seed, uow, Role.DOCTOR, 1)
        invite(seed, uow, Role.DOCTOR, 2)
        with pytest.raises(QuotaExceeded) as exc:
            invite(seed, uow, Role.DOCTOR, 3)
        assert (exc.value.code, exc.value.params["limit"]) == ("plan.quota_doctors", 3)

    def test_extra_admins_count_as_support(self):
        seed = seed_clinic()
        uow = on_plan(seed, CLINICA)  # 3 support: nurse + receptionist + 1 more
        invite(seed, uow, Role.ADMIN, 1)
        with pytest.raises(QuotaExceeded) as exc:
            invite(seed, uow, Role.ADMIN, 2)
        assert exc.value.code == "plan.quota_support_users"

    def test_override_raises_the_limit(self):
        seed = seed_clinic()
        uow = on_plan(seed, INDEPENDIENTE, LimitOverrides(doctors=2))
        invite(seed, uow, Role.DOCTOR, 1)
        with pytest.raises(QuotaExceeded):
            invite(seed, uow, Role.DOCTOR, 2)

    def test_refused_invite_creates_nothing(self):
        seed = seed_clinic()
        uow = on_plan(seed, INDEPENDIENTE)  # 1 doctor, already used
        with pytest.raises(QuotaExceeded):
            invite(seed, uow, Role.DOCTOR, 1)
        assert uow.users.get_by_email("nuevo1-doctor@norte.test") is None


class TestReactivateAndRoles:
    def test_reactivating_needs_a_free_seat(self):
        seed = seed_clinic()
        uow = on_plan(seed, CLINICA)
        SuspendUser(uow, FixedClock()).execute(seed.actor(seed.admin), seed.nurse.id)
        invite(seed, uow, Role.NURSE, 1)
        invite(seed, uow, Role.NURSE, 2)  # support: receptionist + 2 new = 3
        with pytest.raises(QuotaExceeded):
            ReactivateUser(uow, FixedClock()).execute(seed.actor(seed.admin), seed.nurse.id)

    def test_role_change_moves_the_seat(self):
        seed = seed_clinic()
        uow = on_plan(seed, INDEPENDIENTE)  # 1 doctor (used), 1 support (2 used)
        with pytest.raises(QuotaExceeded):
            UpdateUserRole(uow, FixedClock()).execute(
                seed.actor(seed.admin), seed.nurse.id, Role.DOCTOR
            )
        # doctor → nurse frees a doctor seat; support is already over and doesn't shrink
        with pytest.raises(QuotaExceeded):
            UpdateUser(uow, FixedClock()).execute(
                seed.actor(seed.admin), seed.doctor.id, role=Role.NURSE
            )

    def test_over_the_limit_clinic_can_still_move_seats_down(self):
        seed = seed_clinic()
        uow = on_plan(seed, CLINICA, LimitOverrides(support_users=1))  # 2 support used
        # nurse → doctor: support shrinks, doctors grow within their limit
        user = UpdateUserRole(uow, FixedClock()).execute(
            seed.actor(seed.admin), seed.nurse.id, Role.DOCTOR
        )
        assert user.role == Role.DOCTOR

    def test_profile_edit_without_role_change_is_never_blocked(self):
        seed = seed_clinic()
        uow = on_plan(seed, INDEPENDIENTE)  # support over the limit
        UpdateUser(uow, FixedClock()).execute(
            seed.actor(seed.admin), seed.nurse.id, name="Otra", role=Role.NURSE
        )


class TestPlatformSide:
    def test_console_respects_quotas_too(self):
        seed = seed_clinic()
        actor = PlatformActorContext(admin_id=seed.platform_admin.id)
        on_plan(seed, INDEPENDIENTE)
        with pytest.raises(QuotaExceeded):
            UpdateTenantUser(seed.factory, FixedClock()).execute(
                actor, seed.tenant.id, seed.nurse.id, role=Role.DOCTOR
            )
        uow = seed.factory.for_tenant(seed.tenant.id)
        SuspendUser(uow, FixedClock()).execute(seed.actor(seed.admin), seed.doctor.id)
        invite(seed, uow, Role.DOCTOR, 1)
        with pytest.raises(QuotaExceeded):
            UnlockUser(seed.factory, FixedClock()).execute(actor, seed.tenant.id, seed.doctor.id)


class TestLocations:
    def test_sites_up_to_the_limit(self):
        seed = seed_clinic()
        uow = on_plan(seed, CLINICA, LimitOverrides(locations=2))
        AddLocation(uow, FixedClock()).execute(seed.actor(seed.admin), name="Sede 2")
        with pytest.raises(QuotaExceeded) as exc:
            AddLocation(uow, FixedClock()).execute(seed.actor(seed.admin), name="Sede 3")
        assert exc.value.code == "plan.quota_locations"
        assert len(uow.tenants.get_by_id(seed.tenant.id).locations) == 2
