"""A clinic always keeps at least one active administrator."""

from __future__ import annotations

from collections.abc import Collection

from medicore.domain.shared.errors import LastAdminRequired
from medicore.domain.shared.identifiers import UserId


def ensure_admin_remains(
    active_admins: Collection[UserId], user_id: UserId, *, stays_admin: bool
) -> None:
    if stays_admin or user_id not in active_admins:
        return
    if len(active_admins) <= 1:
        raise LastAdminRequired("the clinic must keep at least one active administrator")
