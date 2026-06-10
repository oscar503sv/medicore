"""Per-tenant role-permission customization: matrix, overrides, guardrails, resolution."""

from __future__ import annotations

import pytest

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import (
    Permission,
    effective_permissions,
    ensure_permission,
    permissions_for,
)
from medicore.application.use_cases.auth import AuthenticateUser, AuthenticateUserCommand
from medicore.application.use_cases.platform import (
    GetTenantPermissionsMatrix,
    ResetTenantRolePermissions,
    UpdateTenantRolePermissions,
)
from medicore.application.use_cases.role_permissions import (
    GetPermissionsMatrix,
    ResetRolePermissions,
    UpdateRolePermissions,
)
from medicore.domain.enums import Role
from medicore.domain.shared.errors import PermissionDenied
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher


def _platform_actor(seed):
    from medicore.application.common.context import PlatformActorContext

    return PlatformActorContext(admin_id=seed.platform_admin.id)


def _receptionist_defaults() -> list[str]:
    return sorted(str(p) for p in permissions_for(Role.RECEPTIONIST))


class TestMatrix:
    def test_defaults_when_no_override(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        matrix = GetPermissionsMatrix(uow).execute(seed.actor(seed.admin))
        for role in Role:
            entry = matrix.roles[role]
            assert entry.customized is False
            assert entry.effective == entry.defaults
        assert matrix.catalog == tuple(sorted(str(p) for p in Permission))

    def test_requires_permissions_manage(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            GetPermissionsMatrix(uow).execute(seed.doctor_actor)


class TestUpdate:
    def test_override_round_trip(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        smaller = [p for p in _receptionist_defaults() if p != "appointments.manage"]

        matrix = UpdateRolePermissions(uow, FixedClock()).execute(
            admin, Role.RECEPTIONIST, smaller
        )
        entry = matrix.roles[Role.RECEPTIONIST]
        assert entry.customized is True
        assert "appointments.manage" not in entry.effective
        assert "appointments.manage" in entry.defaults
        assert uow.audit.query(action="permissions.updated")

    def test_reset_restores_defaults(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        UpdateRolePermissions(uow, FixedClock()).execute(
            admin, Role.RECEPTIONIST, ["patients.view"]
        )
        matrix = ResetRolePermissions(uow, FixedClock()).execute(admin, Role.RECEPTIONIST)
        entry = matrix.roles[Role.RECEPTIONIST]
        assert entry.customized is False
        assert entry.effective == entry.defaults
        assert uow.audit.query(action="permissions.reset")

    def test_admin_role_is_not_customizable(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        with pytest.raises(ValidationError):
            UpdateRolePermissions(uow, FixedClock()).execute(admin, Role.ADMIN, [])
        with pytest.raises(ValidationError):
            ResetRolePermissions(uow, FixedClock()).execute(admin, Role.ADMIN)

    def test_sign_cannot_be_granted_to_nurse(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(ValidationError):
            UpdateRolePermissions(uow, FixedClock()).execute(
                seed.actor(seed.admin), Role.NURSE, ["records.sign"]
            )

    def test_sign_cannot_be_removed_from_doctor(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        no_sign = [
            str(p) for p in permissions_for(Role.DOCTOR) if p != Permission.RECORDS_SIGN
        ]
        with pytest.raises(ValidationError):
            UpdateRolePermissions(uow, FixedClock()).execute(
                seed.actor(seed.admin), Role.DOCTOR, no_sign
            )

    def test_unknown_permission_rejected_on_write(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(ValidationError):
            UpdateRolePermissions(uow, FixedClock()).execute(
                seed.actor(seed.admin), Role.NURSE, ["patients.view", "not.a.permission"]
            )


class TestResolution:
    def test_effective_permissions_filters_stale_strings(self):
        effective = effective_permissions(
            Role.NURSE, ["patients.view", "ghost.permission"]
        )
        assert effective == frozenset({Permission.PATIENTS_VIEW})

    def test_ensure_permission_honors_actor_permissions_over_defaults(self):
        seed = seed_clinic()
        # A receptionist whose tenant revoked appointments.manage: defaults would allow it.
        actor = ActorContext(
            user_id=seed.receptionist.id,
            tenant_id=seed.tenant.id,
            role=Role.RECEPTIONIST,
            permissions=frozenset({"patients.view"}),
        )
        ensure_permission(actor, Permission.PATIENTS_VIEW)
        with pytest.raises(PermissionDenied):
            ensure_permission(actor, Permission.APPOINTMENTS_MANAGE)

    def test_login_reflects_override(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        UpdateRolePermissions(uow, FixedClock()).execute(
            seed.actor(seed.admin), Role.RECEPTIONIST, ["patients.view", "diagnoses.view"]
        )
        session = AuthenticateUser(
            seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock()
        ).execute(
            AuthenticateUserCommand(
                slug=str(seed.tenant.slug), email=seed.receptionist.email, password=PASSWORD
            )
        )
        assert session.permissions == ("diagnoses.view", "patients.view")


class TestPlatformVariants:
    def test_platform_update_and_reset(self):
        seed = seed_clinic()
        actor = _platform_actor(seed)
        smaller = [p for p in _receptionist_defaults() if p != "appointments.manage"]

        matrix = UpdateTenantRolePermissions(seed.factory, FixedClock()).execute(
            actor, seed.tenant.id, Role.RECEPTIONIST, smaller
        )
        assert matrix.roles[Role.RECEPTIONIST].customized is True
        audit = [
            e
            for e in seed.factory.platform_uow().platform_audit.list()
            if e.action == "permissions.updated"
        ]
        assert audit and audit[0].tenant_id == seed.tenant.id

        matrix = ResetTenantRolePermissions(seed.factory, FixedClock()).execute(
            actor, seed.tenant.id, Role.RECEPTIONIST
        )
        assert matrix.roles[Role.RECEPTIONIST].customized is False

    def test_platform_read_matrix(self):
        seed = seed_clinic()
        matrix = GetTenantPermissionsMatrix(seed.factory).execute(
            _platform_actor(seed), seed.tenant.id
        )
        assert matrix.roles[Role.ADMIN].customized is False

    def test_platform_respects_guardrails(self):
        seed = seed_clinic()
        actor = _platform_actor(seed)
        with pytest.raises(ValidationError):
            UpdateTenantRolePermissions(seed.factory, FixedClock()).execute(
                actor, seed.tenant.id, Role.ADMIN, []
            )
