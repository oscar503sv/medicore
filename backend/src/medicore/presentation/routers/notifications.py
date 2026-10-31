"""Notifications router: the authenticated user's own inbox."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.notifications import (
    CountMyUnreadNotifications,
    ListMyNotifications,
    MarkAllNotificationsRead,
    MarkNotificationRead,
)
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.identifiers import NotificationId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.notifications import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from medicore.presentation.serializers import ser_notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    actor: Actor,
    uow: UoW,
    unread_only: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    items = ListMyNotifications(uow).execute(
        actor, unread_only, Paging(offset=offset, limit=limit)
    )
    unread = CountMyUnreadNotifications(uow).execute(actor)
    return NotificationListResponse(
        items=[ser_notification(n) for n in items], unread_count=unread
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(actor: Actor, uow: UoW):
    return UnreadCountResponse(unread_count=CountMyUnreadNotifications(uow).execute(actor))


@router.post("/read-all", response_model=MarkAllReadResponse)
def mark_all_read(actor: Actor, uow: UoW, clock: Clock):
    return MarkAllReadResponse(marked=MarkAllNotificationsRead(uow, clock).execute(actor))


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: str, actor: Actor, uow: UoW, clock: Clock):
    notification = MarkNotificationRead(uow, clock).execute(
        actor, NotificationId.parse(notification_id)
    )
    return ser_notification(notification)
