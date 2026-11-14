"""A clinic always keeps at least one active administrator."""

from __future__ import annotations

import pytest

from medicore.domain.services.admin_continuity import ensure_admin_remains
from medicore.domain.shared.errors import LastAdminRequired
from medicore.domain.shared.identifiers import UserId

A, B, OTHER = UserId.new(), UserId.new(), UserId.new()


@pytest.mark.parametrize(
    ("active_admins", "user_id", "stays_admin"),
    [
        ([A], A, True),
        ([A], OTHER, False),
        ([A, B], A, False),
        ([], A, False),
    ],
    ids=["stays-admin", "not-an-active-admin", "another-admin-remains", "no-admins-listed"],
)
def test_change_that_leaves_an_admin_is_allowed(active_admins, user_id, stays_admin):
    ensure_admin_remains(active_admins, user_id, stays_admin=stays_admin)


def test_removing_the_only_admin_is_refused():
    with pytest.raises(LastAdminRequired) as exc:
        ensure_admin_remains([A], A, stays_admin=False)
    assert exc.value.code == "users.last_admin"
