"""PlatformAdmin aggregate — a superadmin that administers tenants across the platform.

Unlike :class:`User`, a platform admin belongs to **no tenant**: it lives above the multi-tenant
boundary and is authenticated through a separate flow (email + password, no organization slug).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.entities.user import derive_initials
from medicore.domain.enums import UserStatus
from medicore.domain.shared.identifiers import PlatformAdminId


@dataclass(slots=True)
class PlatformAdmin:
    """A platform-level superadmin account."""

    id: PlatformAdminId
    name: str
    email: str  # globally unique
    password_hash: str
    status: UserStatus = UserStatus.ACTIVE
    last_seen_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def avatar_initials(self) -> str:
        return derive_initials(self.name)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def change_password(self, new_hash: str) -> None:
        self.password_hash = new_hash
