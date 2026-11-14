"""User aggregate rules."""

from __future__ import annotations

from medicore.domain.enums import Role
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments
from tests.support.builders import build_tenant, build_user


def _user_with_adjustments(role: Role):
    user = build_user(build_tenant().id, role)
    user.adjust_permissions(PermissionAdjustments(granted=frozenset({"audit.view"})))
    return user


def test_changing_to_another_role_clears_the_adjustments():
    user = _user_with_adjustments(Role.NURSE)

    user.change_role(Role.RECEPTIONIST)

    assert user.role == Role.RECEPTIONIST
    assert user.permission_adjustments.is_empty


def test_keeping_the_same_role_keeps_the_adjustments():
    user = _user_with_adjustments(Role.NURSE)

    user.change_role(Role.NURSE)

    assert not user.permission_adjustments.is_empty


def test_email_is_normalized_on_construction():
    user = build_user(build_tenant().id, Role.NURSE, email="  Nurse@Clinic.TEST ")

    assert user.email == "nurse@clinic.test"
