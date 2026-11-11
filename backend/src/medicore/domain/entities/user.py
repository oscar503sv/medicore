"""User aggregate (access account) and the DoctorProfile entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import LangPref, Role, Sex, ThemePref, UserStatus
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import (
    DoctorProfileId,
    LocationId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.permission_adjustments import PermissionAdjustments
from medicore.domain.value_objects.user_preferences import UserPreferences


def derive_initials(name: str) -> str:
    """Avatar initials from a person's name, e.g. 'Ana López' → 'AL'."""
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


JVPM_MAX_DIGITS = 10


def normalize_jvpm(value: str | None) -> str | None:
    """A doctor's registration number with the Junta de Vigilancia de la Profesión Médica,
    printed on prescriptions and certificates: digits only; blank clears it."""
    if value is None or not value.strip():
        return None
    number = value.strip()
    if not number.isdigit() or len(number) > JVPM_MAX_DIGITS:
        raise InvalidValueObject("the JVPM number must be digits only", code="user.invalid_jvpm",
                                 max=JVPM_MAX_DIGITS)
    return number


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
    sex: Sex | None = None
    specialty: str | None = None
    phone: str | None = None
    jvpm: str | None = None  # doctors: registration number printed on their documents
    must_change_password: bool = False
    preferences: UserPreferences = field(default_factory=UserPreferences)
    # Exceptions to the role's permissions (only honored on plans with per-user permissions).
    permission_adjustments: PermissionAdjustments = field(default_factory=PermissionAdjustments)
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

    def adjust_permissions(self, adjustments: PermissionAdjustments) -> None:
        self.permission_adjustments = adjustments

    def change_password(self, new_hash: str) -> None:
        """Set a new password hash and clear any pending forced-change flag."""
        self.password_hash = new_hash
        self.must_change_password = False

    def set_temporary_password(self, new_hash: str) -> None:
        """Set a temporary password hash and require the user to change it on next login."""
        self.password_hash = new_hash
        self.must_change_password = True

    def set_theme(self, theme: ThemePref) -> None:
        from dataclasses import replace

        self.preferences = replace(self.preferences, theme=theme)

    def set_language(self, language: LangPref) -> None:
        from dataclasses import replace

        self.preferences = replace(self.preferences, language=language)

    def mark_welcome_seen(self) -> None:
        from dataclasses import replace

        self.preferences = replace(self.preferences, welcome_seen=True)

    def dismiss_onboarding(self) -> None:
        from dataclasses import replace

        self.preferences = replace(self.preferences, welcome_seen=True, onboarding_dismissed=True)


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
