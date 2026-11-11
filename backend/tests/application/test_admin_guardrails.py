"""What stays with administrators and what stays with Medicore support.

* Only an admin acts on admin accounts or makes someone an admin: a delegated
  ``users.manage`` manages the rest of the staff, never the admins.
* ``permissions.manage`` is admin-only: it can't be delegated to a role or a user.
* The timezone is set by the platform console; sites are self-service within the plan
  (``locations.manage``) and the console can open them too.
"""

from __future__ import annotations

import dataclasses

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import (
    Permission,
    granted,
    permissions_for,
)
from medicore.application.use_cases.organization import (
    AddLocation,
    UpdateLocation,
    UpdateOrganization,
)
from medicore.application.use_cases.platform import AddTenantLocation
from medicore.application.use_cases.role_permissions import UpdateRolePermissions
from medicore.application.use_cases.sessions import RevokeAllUserSessions
from medicore.application.use_cases.user_permissions import UpdateUserPermissions
from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    ReactivateUser,
    ResetUserPassword,
    ResetUserPasswordCommand,
    SuspendUser,
    UpdateUser,
    UpdateUserRole,
)
from medicore.domain.enums import AddonModule, Role
from medicore.domain.services.plan_catalog import CLINICA
from medicore.domain.shared.errors import PermissionDenied, QuotaExceeded
from medicore.domain.value_objects.plan_limits import LimitOverrides
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, PlainPasswordHasher


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _delegated(seed, *extra: Permission):
    """A receptionist who was handed management permissions."""
    perms = {str(p) for p in permissions_for(Role.RECEPTIONIST)} | {str(p) for p in extra}
    return dataclasses.replace(seed.actor(seed.receptionist), permissions=frozenset(perms))


class TestOnlyAdminsActOnAdmins:
    @pytest.fixture
    def seed(self):
        return seed_clinic()

    @pytest.fixture
    def manager(self, seed):
        return _delegated(seed, Permission.USERS_MANAGE)

    def _denied(self, call):
        with pytest.raises(PermissionDenied) as exc:
            call()
        assert exc.value.code == "users.admin_only"

    def test_cannot_invite_an_admin(self, seed, manager):
        cmd = InviteUserCommand(name="X", email="x@n.test", role=Role.ADMIN, password="secret123")
        use_case = InviteUser(_uow(seed), PlainPasswordHasher(), FixedClock())
        self._denied(lambda: use_case.execute(manager, cmd))

    def test_cannot_promote_to_admin(self, seed, manager):
        self._denied(
            lambda: UpdateUserRole(_uow(seed), FixedClock()).execute(
                manager, seed.nurse.id, Role.ADMIN
            )
        )
        self._denied(
            lambda: UpdateUser(_uow(seed), FixedClock()).execute(
                manager, seed.nurse.id, role=Role.ADMIN
            )
        )

    def test_cannot_touch_an_admin_account(self, seed, manager):
        uow, clock, admin_id = _uow(seed), FixedClock(), seed.admin.id
        self._denied(lambda: UpdateUser(uow, clock).execute(manager, admin_id, name="Y"))
        self._denied(lambda: UpdateUserRole(uow, clock).execute(manager, admin_id, Role.NURSE))
        self._denied(lambda: SuspendUser(uow, clock).execute(manager, admin_id))
        self._denied(lambda: ReactivateUser(uow, clock).execute(manager, admin_id))
        self._denied(lambda: RevokeAllUserSessions(uow, clock).execute(manager, admin_id))
        self._denied(
            lambda: ResetUserPassword(uow, PlainPasswordHasher(), clock).execute(
                manager, ResetUserPasswordCommand(user_id=admin_id, password="takeover1")
            )
        )

    def test_still_manages_the_rest_of_the_staff(self, seed, manager):
        user = UpdateUser(_uow(seed), FixedClock()).execute(manager, seed.nurse.id, name="Ana")
        assert user.name == "Ana"

    def test_an_admin_manages_other_admins(self, seed):
        user = UpdateUserRole(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), seed.nurse.id, Role.ADMIN
        )
        assert user.role == Role.ADMIN


class TestPermissionsManageIsAdminOnly:
    def test_role_customization_rejects_it(self):
        seed = seed_clinic()
        wanted = [str(p) for p in permissions_for(Role.RECEPTIONIST)] + ["permissions.manage"]
        with pytest.raises(ValidationError) as exc:
            UpdateRolePermissions(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), Role.RECEPTIONIST, wanted
            )
        assert exc.value.code == "roles.admin_only"

    def test_user_permissions_reject_it(self):
        seed = seed_clinic()
        wanted = [str(p) for p in permissions_for(Role.NURSE)] + ["permissions.manage"]
        with pytest.raises(ValidationError) as exc:
            UpdateUserPermissions(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), seed.nurse.id, wanted
            )
        assert exc.value.code == "roles.admin_only"

    def test_a_stored_grant_never_applies(self):
        """Overrides saved before this rule can't keep it alive."""
        perms = granted(Role.RECEPTIONIST, ["patients.view", "permissions.manage"], AddonModule)
        assert Permission.PERMISSIONS_MANAGE not in perms
        assert Permission.PERMISSIONS_MANAGE in granted(Role.ADMIN, None, AddonModule)


class TestOrganization:
    def test_timezone_is_changed_by_support(self):
        seed = seed_clinic()
        with pytest.raises(PermissionDenied) as exc:
            UpdateOrganization(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), timezone="America/El_Salvador"
            )
        assert exc.value.code == "organization.timezone_locked"

    def test_unchanged_timezone_and_other_fields_still_save(self):
        seed = seed_clinic()
        tenant = UpdateOrganization(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), legal_name="Clínica Sur", timezone=seed.tenant.timezone
        )
        assert tenant.legal_name == "Clínica Sur"

    def test_sites_need_their_own_permission(self):
        seed = seed_clinic()
        org_only = _delegated(seed, Permission.ORGANIZATION_MANAGE)
        with pytest.raises(PermissionDenied):
            AddLocation(_uow(seed), FixedClock()).execute(org_only, name="Sede 2")
        location_id = seed.tenant.locations[0].id
        with pytest.raises(PermissionDenied):
            UpdateLocation(_uow(seed), FixedClock()).execute(org_only, location_id, name="X")
        sites = _delegated(seed, Permission.LOCATIONS_MANAGE)
        tenant = AddLocation(_uow(seed), FixedClock()).execute(sites, name="Sede 2")
        assert len(tenant.locations) == 2

    def test_console_opens_sites_within_the_plan(self):
        seed = seed_clinic()
        uow = _uow(seed)
        tenant = uow.tenants.get_by_id(seed.tenant.id)
        tenant.subscription = Subscription(
            plan_code=CLINICA, limit_overrides=LimitOverrides(locations=2)
        )
        uow.tenants.save(tenant)
        actor = PlatformActorContext(admin_id=seed.platform_admin.id)
        use_case = AddTenantLocation(seed.factory, FixedClock())
        tenant = use_case.execute(actor, seed.tenant.id, name="Sede Norte", address="Calle 1")
        assert [loc.name for loc in tenant.locations][-1] == "Sede Norte"
        with pytest.raises(QuotaExceeded):
            use_case.execute(actor, seed.tenant.id, name="Sede 3")
