"""PermissionAdjustments: one user's exceptions to their role."""

from __future__ import annotations

import pytest

from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments


def test_between_keeps_only_the_differences():
    adj = PermissionAdjustments.between({"a", "b", "c"}, {"b", "c", "d"})
    assert adj.granted == {"d"}
    assert adj.revoked == {"a"}


def test_between_equal_sets_is_empty():
    assert PermissionAdjustments.between({"a"}, {"a"}).is_empty
    assert PermissionAdjustments().is_empty


def test_apply_grants_and_revokes():
    adj = PermissionAdjustments(granted=frozenset({"d"}), revoked=frozenset({"a"}))
    assert adj.apply({"a", "b"}) == {"b", "d"}


def test_a_permission_cannot_be_granted_and_revoked():
    with pytest.raises(InvalidValueObject) as exc:
        PermissionAdjustments(granted=frozenset({"x"}), revoked=frozenset({"x"}))
    assert exc.value.code == "user_permissions.conflict"
