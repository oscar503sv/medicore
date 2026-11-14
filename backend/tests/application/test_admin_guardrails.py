"""What stays with administrators and what stays with Medicore support.

* Only an admin acts on admin or doctor accounts or hands out those roles: a delegated
  ``users.manage`` manages the rest of the staff, never the admins or the doctors.
* Nobody manages their own account through the management use cases, admins included.
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
from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from medicore.application.use_cases.organization import (
    AddLocation,
    UpdateLocation,
    UpdateOrganization,
)
from medicore.application.use_cases.platform import AddTenantLocation
from medicore.application.use_cases.role_permissions import UpdateRolePermissions
from medicore.application.use_cases.sessions import (
    ListMySessions,
    ListUserSessions,
    RevokeAllUserSessions,
    RevokeMySession,
    RevokeUserSession,
)
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
from medicore.domain.enums import AddonModule, Role, UserStatus
from medicore.domain.services.plan_catalog import CLINICA
from medicore.domain.shared.errors import PermissionDenied, QuotaExceeded
from medicore.domain.shared.identifiers import SessionId
from medicore.domain.value_objects.plan_limits import LimitOverrides
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher


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


def _login(seed, user):
    session = AuthenticateUser(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock()
    ).execute(
        AuthenticateUserCommand(slug=str(seed.tenant.slug), email=user.email, password=PASSWORD)
    )
    return SessionId.parse(FakeTokenIssuer().decode(session.token).session_id)


class TestOnlyAdminsActOnDoctors:
    @pytest.fixture
    def seed(self):
        return seed_clinic()

    @pytest.fixture
    def manager(self, seed):
        return _delegated(seed, Permission.USERS_MANAGE)

    def _denied(self, call):
        with pytest.raises(PermissionDenied) as exc:
            call()
        assert exc.value.code == "users.doctor_admin_only"

    def test_cannot_invite_a_doctor(self, seed, manager):
        cmd = InviteUserCommand(name="X", email="x@n.test", role=Role.DOCTOR, password="secret123")
        use_case = InviteUser(_uow(seed), PlainPasswordHasher(), FixedClock())
        self._denied(lambda: use_case.execute(manager, cmd))

    def test_cannot_make_someone_a_doctor(self, seed, manager):
        self._denied(
            lambda: UpdateUserRole(_uow(seed), FixedClock()).execute(
                manager, seed.nurse.id, Role.DOCTOR
            )
        )
        self._denied(
            lambda: UpdateUser(_uow(seed), FixedClock()).execute(
                manager, seed.nurse.id, role=Role.DOCTOR
            )
        )
        assert _uow(seed).users.get_by_id(seed.nurse.id).role == Role.NURSE

    def test_cannot_touch_a_doctor_account(self, seed, manager):
        uow, clock, doctor_id = _uow(seed), FixedClock(), seed.doctor.id
        password_hash = seed.doctor.password_hash
        session_id = _login(seed, seed.doctor)
        self._denied(lambda: UpdateUser(uow, clock).execute(manager, doctor_id, name="Y"))
        self._denied(lambda: UpdateUserRole(uow, clock).execute(manager, doctor_id, Role.NURSE))
        self._denied(lambda: SuspendUser(uow, clock).execute(manager, doctor_id))
        self._denied(lambda: ReactivateUser(uow, clock).execute(manager, doctor_id))
        self._denied(lambda: RevokeAllUserSessions(uow, clock).execute(manager, doctor_id))
        self._denied(lambda: RevokeUserSession(uow, clock).execute(manager, doctor_id, session_id))
        self._denied(lambda: ListUserSessions(uow, clock).execute(manager, doctor_id))
        self._denied(
            lambda: ResetUserPassword(uow, PlainPasswordHasher(), clock).execute(
                manager, ResetUserPasswordCommand(user_id=doctor_id, password="takeover1")
            )
        )
        doctor = uow.users.get_by_id(doctor_id)
        assert doctor.status == UserStatus.ACTIVE
        assert doctor.password_hash == password_hash
        assert seed.factory.store.sessions[session_id.value].is_active(clock.now())

    def test_still_invites_and_manages_the_rest_of_the_staff(self, seed, manager):
        cmd = InviteUserCommand(
            name="Rita", email="rita@n.test", role=Role.RECEPTIONIST, password="Clave-Segura-2031"
        )
        invited = InviteUser(_uow(seed), PlainPasswordHasher(), FixedClock()).execute(manager, cmd)
        assert invited.role == Role.RECEPTIONIST
        user = UpdateUserRole(_uow(seed), FixedClock()).execute(
            manager, seed.nurse.id, Role.RECEPTIONIST
        )
        assert user.role == Role.RECEPTIONIST

    def test_an_admin_manages_doctors(self, seed):
        user = UpdateUser(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), seed.doctor.id, name="Dra. Ruiz"
        )
        assert user.name == "Dra. Ruiz"


class TestNobodyManagesTheirOwnAccount:
    @pytest.fixture
    def seed(self):
        return seed_clinic()

    @pytest.fixture
    def manager(self, seed):
        return _delegated(seed, Permission.USERS_MANAGE)

    def _denied(self, call):
        with pytest.raises(PermissionDenied) as exc:
            call()
        assert exc.value.code == "users.self_management"

    def test_delegate_cannot_promote_themselves(self, seed, manager):
        me = seed.receptionist.id
        self._denied(
            lambda: UpdateUserRole(_uow(seed), FixedClock()).execute(manager, me, Role.DOCTOR)
        )
        self._denied(
            lambda: UpdateUser(_uow(seed), FixedClock()).execute(manager, me, role=Role.DOCTOR)
        )
        assert _uow(seed).users.get_by_id(me).role == Role.RECEPTIONIST

    def test_delegate_cannot_change_own_role_even_to_unprotected_one(self, seed, manager):
        self._denied(
            lambda: UpdateUserRole(_uow(seed), FixedClock()).execute(
                manager, seed.receptionist.id, Role.NURSE
            )
        )

    @pytest.mark.parametrize(
        "action",
        [
            "update", "role", "suspend", "reactivate", "reset_password", "revoke_all",
            "revoke_one",
        ],
    )
    def test_admin_cannot_manage_own_account(self, seed, action):
        admin, clock, uow = seed.actor(seed.admin), FixedClock(), _uow(seed)
        me = seed.admin.id
        session_id = _login(seed, seed.admin)
        calls = {
            "update": lambda: UpdateUser(uow, clock).execute(admin, me, name="Y"),
            "role": lambda: UpdateUserRole(uow, clock).execute(admin, me, Role.NURSE),
            "suspend": lambda: SuspendUser(uow, clock).execute(admin, me),
            "reactivate": lambda: ReactivateUser(uow, clock).execute(admin, me),
            "reset_password": lambda: ResetUserPassword(uow, PlainPasswordHasher(), clock).execute(
                admin, ResetUserPasswordCommand(user_id=me, password="takeover1")
            ),
            "revoke_all": lambda: RevokeAllUserSessions(uow, clock).execute(admin, me),
            "revoke_one": lambda: RevokeUserSession(uow, clock).execute(admin, me, session_id),
        }
        password_hash = seed.admin.password_hash
        self._denied(calls[action])
        current = uow.users.get_by_id(me)
        assert current.status == UserStatus.ACTIVE
        assert current.role == Role.ADMIN
        assert current.password_hash == password_hash
        assert seed.factory.store.sessions[session_id.value].is_active(clock.now())

    def test_permission_is_checked_before_self(self, seed):
        me = seed.actor(seed.receptionist)
        with pytest.raises(PermissionDenied) as exc:
            SuspendUser(_uow(seed), FixedClock()).execute(me, seed.receptionist.id)
        assert exc.value.code == "permission.missing"

    def test_admin_may_list_own_sessions_via_admin_endpoint(self, seed):
        _login(seed, seed.admin)
        listed = ListUserSessions(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), seed.admin.id
        )
        assert len(listed) == 1

    def test_own_sessions_stay_self_service(self, seed, manager):
        session_id = _login(seed, seed.receptionist)
        clock = FixedClock()
        assert len(ListMySessions(_uow(seed), clock).execute(manager)) == 1
        RevokeMySession(_uow(seed), clock).execute(manager, session_id)
        assert ListMySessions(_uow(seed), clock).execute(manager) == []


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
