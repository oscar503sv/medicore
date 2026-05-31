"""User aggregate (access account) and the DoctorProfile entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import LangPref, Role, ThemePref, UserStatus
from medicore.domain.shared.identifiers import (
    DoctorProfileId,
    LocationId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.user_preferences import UserPreferences


def derive_initials(name: str) -> str:
    """Avatar initials from a person's name, e.g. 'Ana López' → 'AL'."""
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


@dataclass(slots=True)
class User:
    """An access account belonging to exactly one tenant."""

    id: UserId
    tenant_id: TenantId
    name: str
    email: str  # unique within the tenant (enforced at repository level)
    password_hash: str
    role: Role
    status: UserStatus = UserStatus.PENDING
    specialty: str | None = None
    phone: str | None = None
    preferences: UserPreferences = field(default_factory=UserPreferences)
    last_seen_at: datetime | None = None
    joined_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def avatar_initials(self) -> str:
        return derive_initials(self.name)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def activate(self) -> None:
        self.status = UserStatus.ACTIVE

    def suspend(self) -> None:
        self.status = UserStatus.SUSPENDED

    def change_role(self, role: Role) -> None:
        self.role = role

    def set_theme(self, theme: ThemePref) -> None:
        from dataclasses import replace

        self.preferences = replace(self.preferences, theme=theme)

    def set_language(self, language: LangPref) -> None:
        from dataclasses import replace

        self.preferences = replace(self.preferences, language=language)


@dataclass(slots=True)
class DoctorProfile:
    """Clinical profile for a doctor user (1:1 with User when role == doctor).

    Owns the doctor's availability via the DoctorAvailability aggregate (referenced by id).
    """

    id: DoctorProfileId
    user_id: UserId
    tenant_id: TenantId
    bio: str | None = None
    default_location_id: LocationId | None = None
