"""Notification aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.shared.identifiers import NotificationId, TenantId, UserId


@dataclass(slots=True)
class Notification:
    """An in-app notification addressed to a user within a tenant.

    Stores *what happened* (``type`` + ``data``), never rendered text: the client renders it
    in the user's language. ``data`` holds plain strings only — ids for linking and display
    labels (names, codes, dates) frozen at emission time. Never clinical content.
    """

    id: NotificationId
    tenant_id: TenantId
    user_id: UserId
    type: str
    data: dict[str, str] = field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self, when: datetime | None = None) -> None:
        if self.read_at is None:
            self.read_at = when or datetime.now(UTC)
