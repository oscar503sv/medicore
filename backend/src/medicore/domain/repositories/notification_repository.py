"""NotificationRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.notification import Notification
from medicore.domain.shared.identifiers import NotificationId, UserId


class NotificationRepository(Protocol):
    def list_by_user(self, user_id: UserId, unread_only: bool = False) -> list[Notification]: ...

    def mark_read(self, notification_id: NotificationId) -> None: ...

    def save(self, notification: Notification) -> None: ...
