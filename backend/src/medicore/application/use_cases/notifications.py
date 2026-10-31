"""Notification inbox use cases: a user reads and acknowledges their own notifications.

No permission is required — every query is scoped to the actor. While a superadmin is
impersonating the clinic, reads are allowed but marking as read is a no-op, so support work
never consumes the real user's unread notifications.
"""

from __future__ import annotations

from datetime import timedelta

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.notification import Notification
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.identifiers import NotificationId

# Read notifications older than this are pruned whenever the user acknowledges something.
READ_RETENTION = timedelta(days=90)


class ListMyNotifications:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, unread_only: bool = False, paging: Paging | None = None
    ) -> list[Notification]:
        with self._uow:
            return self._uow.notifications.list_by_user(actor.user_id, unread_only, paging)


class CountMyUnreadNotifications:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> int:
        with self._uow:
            return self._uow.notifications.count_unread(actor.user_id)


class MarkNotificationRead:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, notification_id: NotificationId) -> Notification:
        with self._uow:
            notification = self._uow.notifications.get_by_id(notification_id)
            # Someone else's notification is indistinguishable from a missing one.
            if notification is None or notification.user_id != actor.user_id:
                raise EntityNotFound("Notification", notification_id)
            if actor.impersonated_by is not None or notification.is_read:
                return notification
            now = self._clock.now()
            notification.mark_read(now)
            self._uow.notifications.save(notification)
            self._uow.notifications.delete_read_before(actor.user_id, now - READ_RETENTION)
            self._uow.commit()
        return notification


class MarkAllNotificationsRead:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext) -> int:
        """Returns how many notifications were marked as read."""
        if actor.impersonated_by is not None:
            return 0
        with self._uow:
            now = self._clock.now()
            changed = self._uow.notifications.mark_all_read(actor.user_id, now)
            self._uow.notifications.delete_read_before(actor.user_id, now - READ_RETENTION)
            self._uow.commit()
        return changed
