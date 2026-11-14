"""The clinic keeps at least one active administrator, from the clinic and the console."""

from __future__ import annotations

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.use_cases.platform import SuspendTenantUser, UpdateTenantUser
from medicore.application.use_cases.users import SuspendUser, UpdateUser, UpdateUserRole
from medicore.domain.enums import Role, UserStatus
from medicore.domain.shared.errors import LastAdminRequired
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock


@pytest.fixture
def seed():
    return seed_clinic()


@pytest.fixture
def second_admin(seed):
    admin = build_user(seed.tenant.id, Role.ADMIN, name="Second Admin", email="admin2@clinica.test")
    seed.factory.store.users[admin.id.value] = admin
    return admin


def _console(seed) -> PlatformActorContext:
    return PlatformActorContext(admin_id=seed.platform_admin.id)


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


class TestConsole:
    def test_cannot_suspend_the_only_admin(self, seed):
        with pytest.raises(LastAdminRequired):
            SuspendTenantUser(seed.factory, FixedClock()).execute(
                _console(seed), seed.tenant.id, seed.admin.id
            )
        assert seed.admin.status == UserStatus.ACTIVE

    def test_cannot_demote_the_only_admin(self, seed):
        with pytest.raises(LastAdminRequired):
            UpdateTenantUser(seed.factory, FixedClock()).execute(
                _console(seed), seed.tenant.id, seed.admin.id, role=Role.DOCTOR
            )
        assert seed.admin.role == Role.ADMIN

    def test_keeping_the_admin_role_is_not_a_demotion(self, seed):
        UpdateTenantUser(seed.factory, FixedClock()).execute(
            _console(seed), seed.tenant.id, seed.admin.id, role=Role.ADMIN, name="Renamed"
        )
        assert seed.admin.name == "Renamed"

    def test_suspends_one_of_two_admins_but_not_the_last(self, seed, second_admin):
        use_case = SuspendTenantUser(seed.factory, FixedClock())
        use_case.execute(_console(seed), seed.tenant.id, second_admin.id)
        assert second_admin.status == UserStatus.SUSPENDED
        with pytest.raises(LastAdminRequired):
            use_case.execute(_console(seed), seed.tenant.id, seed.admin.id)
        assert seed.admin.status == UserStatus.ACTIVE

    def test_suspending_a_non_admin_is_unaffected(self, seed):
        SuspendTenantUser(seed.factory, FixedClock()).execute(
            _console(seed), seed.tenant.id, seed.nurse.id
        )
        assert seed.nurse.status == UserStatus.SUSPENDED


class TestClinic:
    def test_admin_demotes_another_admin_while_one_remains(self, seed, second_admin):
        UpdateUserRole(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), second_admin.id, Role.DOCTOR
        )
        assert second_admin.role == Role.DOCTOR

    def test_stale_admin_cannot_demote_the_last_one(self, seed, second_admin):
        # The second admin's session was resolved before they were demoted: the role it
        # carries is stale, which is exactly what a concurrent request looks like.
        stale_actor = seed.actor(second_admin)
        UpdateUserRole(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), second_admin.id, Role.DOCTOR
        )
        with pytest.raises(LastAdminRequired):
            UpdateUserRole(_uow(seed), FixedClock()).execute(
                stale_actor, seed.admin.id, Role.DOCTOR
            )
        assert seed.admin.role == Role.ADMIN

    def test_stale_admin_cannot_suspend_the_last_one(self, seed, second_admin):
        stale_actor = seed.actor(second_admin)
        SuspendUser(_uow(seed), FixedClock()).execute(seed.actor(seed.admin), second_admin.id)
        with pytest.raises(LastAdminRequired):
            SuspendUser(_uow(seed), FixedClock()).execute(stale_actor, seed.admin.id)
        assert seed.admin.status == UserStatus.ACTIVE

    def test_update_user_cannot_demote_the_last_admin(self, seed, second_admin):
        stale_actor = seed.actor(second_admin)
        UpdateUser(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), second_admin.id, role=Role.NURSE
        )
        with pytest.raises(LastAdminRequired):
            UpdateUser(_uow(seed), FixedClock()).execute(
                stale_actor, seed.admin.id, role=Role.NURSE
            )
