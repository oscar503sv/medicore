"""Per-user permissions: exceptions to a user's role, only on plans that include them."""

from __future__ import annotations

import pytest

from medicore.application.common.entitlements import granted_permissions
from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import Permission, granted
from medicore.application.use_cases.role_permissions import UpdateRolePermissions
from medicore.application.use_cases.user_permissions import (
    GetUserPermissions,
    UpdateUserPermissions,
)
from medicore.domain.enums import AddonModule, Role
from medicore.domain.services.plan_catalog import CLINICA, INDEPENDIENTE
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _on_plan(seed, plan_code: str):
    uow = _uow(seed)
    tenant = uow.tenants.get_by_id(seed.tenant.id)
    tenant.subscription = Subscription(plan_code=plan_code, modules=frozenset(AddonModule))
    uow.tenants.save(tenant)


def _role_set(seed, user) -> list[str]:
    dto = GetUserPermissions(_uow(seed)).execute(seed.actor(seed.admin), user.id)
    return list(dto.role_permissions)


def _update(seed, user, permissions):
    return UpdateUserPermissions(_uow(seed), FixedClock()).execute(
        seed.actor(seed.admin), user.id, permissions
    )


class TestRule:
    def test_adjustments_apply_on_top_of_the_role(self):
        adj = PermissionAdjustments(
            granted=frozenset({"audit.view"}), revoked=frozenset({"patients.view"})
        )
        perms = granted(Role.RECEPTIONIST, None, frozenset(AddonModule), adj)
        assert Permission.AUDIT_VIEW in perms
        assert Permission.PATIENTS_VIEW not in perms

    def test_doctor_only_is_never_granted_to_others(self):
        adj = PermissionAdjustments(granted=frozenset({"records.sign"}))
        assert Permission.RECORDS_SIGN not in granted(
            Role.NURSE, None, frozenset(AddonModule), adj
        )

    def test_uncontracted_modules_stay_locked(self):
        adj = PermissionAdjustments(granted=frozenset({"procedures.view"}))
        assert Permission.PROCEDURES_VIEW not in granted(Role.NURSE, None, frozenset(), adj)

    def test_plan_without_the_feature_ignores_stored_adjustments(self):
        seed = seed_clinic()
        _update(seed, seed.receptionist, ["patients.view"])
        _on_plan(seed, INDEPENDIENTE)
        uow = _uow(seed)
        with uow:
            tenant = uow.tenants.get_by_id(seed.tenant.id)
            user = uow.users.get_by_id(seed.receptionist.id)
            perms = granted_permissions(uow, tenant, user)
        assert Permission.APPOINTMENTS_MANAGE in perms  # the role's set, untouched


class TestGet:
    def test_reports_role_effective_and_availability(self):
        seed = seed_clinic()
        dto = GetUserPermissions(_uow(seed)).execute(seed.actor(seed.admin), seed.nurse.id)
        assert dto.available is True
        assert dto.granted == dto.revoked == ()
        assert dto.effective == dto.role_permissions
        assert dto.locked == ()

    def test_requires_permissions_manage(self):
        seed = seed_clinic()
        with pytest.raises(PermissionDenied):
            GetUserPermissions(_uow(seed)).execute(seed.doctor_actor, seed.nurse.id)

    def test_not_available_on_independiente(self):
        seed = seed_clinic()
        _on_plan(seed, INDEPENDIENTE)
        dto = GetUserPermissions(_uow(seed)).execute(seed.actor(seed.admin), seed.nurse.id)
        assert dto.available is False


class TestUpdate:
    def test_stores_only_the_differences_and_audits(self):
        seed = seed_clinic()
        base = _role_set(seed, seed.receptionist)
        wanted = [p for p in base if p != "appointments.manage"] + ["audit.view"]
        dto = _update(seed, seed.receptionist, wanted)
        assert dto.granted == ("audit.view",)
        assert dto.revoked == ("appointments.manage",)
        assert "audit.view" in dto.effective
        assert "appointments.manage" not in dto.effective
        (entry,) = _uow(seed).audit.query(action="user.permissions_updated")
        assert entry.metadata["added"] == ["audit.view"]
        assert entry.metadata["removed"] == ["appointments.manage"]
        assert entry.metadata["customized"] is True

    def test_role_set_resets_the_user(self):
        seed = seed_clinic()
        base = _role_set(seed, seed.receptionist)
        _update(seed, seed.receptionist, base + ["audit.view"])
        dto = _update(seed, seed.receptionist, base)
        assert dto.granted == dto.revoked == ()
        assert _uow(seed).users.get_by_id(seed.receptionist.id).permission_adjustments.is_empty

    def test_role_changes_still_reach_the_user(self):
        seed = seed_clinic()
        base = _role_set(seed, seed.receptionist)
        _update(seed, seed.receptionist, base + ["audit.view"])
        smaller = [p for p in base if p != "patients.view"]
        UpdateRolePermissions(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), Role.RECEPTIONIST, smaller
        )
        dto = GetUserPermissions(_uow(seed)).execute(seed.actor(seed.admin), seed.receptionist.id)
        assert "patients.view" not in dto.effective
        assert "audit.view" in dto.effective

    def test_applies_to_the_users_next_request(self):
        seed = seed_clinic()
        _update(seed, seed.nurse, [*_role_set(seed, seed.nurse), "audit.view"])
        uow = _uow(seed)
        with uow:
            tenant = uow.tenants.get_by_id(seed.tenant.id)
            user = uow.users.get_by_id(seed.nurse.id)
            assert Permission.AUDIT_VIEW in granted_permissions(uow, tenant, user)

    def test_requires_the_plan_feature(self):
        seed = seed_clinic()
        _on_plan(seed, INDEPENDIENTE)
        with pytest.raises(ValidationError) as exc:
            _update(seed, seed.nurse, [])
        assert exc.value.code == "plan.feature_required"

    def test_available_from_clinica(self):
        seed = seed_clinic()
        _on_plan(seed, CLINICA)
        assert _update(seed, seed.nurse, []).revoked

    @pytest.mark.parametrize(
        ("who", "code"),
        [("admin", "user_permissions.self"), ("other_admin", "user_permissions.admin")],
    )
    def test_admins_and_self_are_not_customizable(self, who, code):
        seed = seed_clinic()
        target = seed.admin
        if who == "other_admin":
            uow = _uow(seed)
            target = uow.users.get_by_id(seed.nurse.id)
            target.role = Role.ADMIN
            uow.users.save(target)
        with pytest.raises(ValidationError) as exc:
            _update(seed, target, [])
        assert exc.value.code == code

    def test_requires_permissions_manage(self):
        seed = seed_clinic()
        with pytest.raises(PermissionDenied):
            UpdateUserPermissions(_uow(seed), FixedClock()).execute(
                seed.doctor_actor, seed.nurse.id, []
            )

    def test_rejects_unknown_permissions(self):
        seed = seed_clinic()
        with pytest.raises(ValidationError) as exc:
            _update(seed, seed.nurse, ["teleport.use"])
        assert exc.value.code == "roles.unknown_permissions"

    def test_doctor_only_rules(self):
        seed = seed_clinic()
        with pytest.raises(ValidationError) as exc:
            _update(seed, seed.nurse, ["records.sign"])
        assert exc.value.code == "roles.doctor_only"
        doctor_set = [p for p in _role_set(seed, seed.doctor) if p != "records.sign"]
        with pytest.raises(ValidationError) as exc:
            _update(seed, seed.doctor, doctor_set)
        assert exc.value.code == "roles.doctor_must_keep"
