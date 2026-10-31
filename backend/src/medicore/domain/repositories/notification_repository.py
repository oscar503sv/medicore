"""NotificationRepository port."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from medicore.domain.entities.notification import Notification
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.identifiers import NotificationId, UserId


class NotificationRepository(Protocol):
    def get_by_id(self, notification_id: NotificationId) -> Notification | None: ...

    def list_by_user(
        self,
        user_id: UserId,
        unread_only: bool = False,
        paging: Paging | None = None,
        category: str | None = None,
    ) -> list[Notification]:
        """Newest first. ``category`` keeps the types starting with ``"<category>."``
        (e.g. ``"appointment"`` → ``appointment.created``, ``appointment.cancelled``…)."""
        ...

    def count_unread(self, user_id: UserId) -> int: ...

    def mark_all_read(self, user_id: UserId, when: datetime) -> int:
        """Mark every unread notification of the user as read; returns how many changed."""
        ...

    def delete_read_before(self, user_id: UserId, cutoff: datetime) -> int:
        """Retention: drop the user's notifications read before ``cutoff``."""
        ...

    def save(self, notification: Notification) -> None: ...
