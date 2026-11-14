"""PlatformAdmin aggregate — a superadmin that administers tenants across the platform.

Unlike :class:`User`, a platform admin belongs to **no tenant**: it lives above the multi-tenant
boundary and is authenticated through a separate flow (email + password, no organization slug).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.entities.user import derive_initials
from medicore.domain.enums import UserStatus
from medicore.domain.shared.errors import DomainError
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
    # Both secrets are stored sealed (encrypted); the domain never sees them in the clear.
    mfa_secret: str | None = None
    mfa_pending_secret: str | None = None  # generated, not yet confirmed with a code
    mfa_enabled_at: datetime | None = None
    # Time step of the last accepted TOTP code: a code is single-use (anti-replay).
    mfa_last_step: int | None = None

    @property
    def avatar_initials(self) -> str:
        return derive_initials(self.name)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def change_password(self, new_hash: str) -> None:
        self.password_hash = new_hash

    @property
    def mfa_enabled(self) -> bool:
        return self.mfa_secret is not None

    def start_mfa_enrollment(self, sealed_secret: str) -> None:
        if self.mfa_enabled:
            raise DomainError("MFA is already enabled", code="mfa.already_enabled")
        self.mfa_pending_secret = sealed_secret

    def confirm_mfa(self, now: datetime, step: int) -> None:
        if self.mfa_pending_secret is None:
            raise DomainError("MFA enrollment was not started", code="mfa.not_enrolling")
        self.mfa_secret = self.mfa_pending_secret
        self.mfa_pending_secret = None
        self.mfa_enabled_at = now
        self.mfa_last_step = step

    def disable_mfa(self) -> None:
        self.mfa_secret = None
        self.mfa_pending_secret = None
        self.mfa_enabled_at = None
        self.mfa_last_step = None

    def accept_totp_step(self, step: int) -> bool:
        """Record ``step`` as used; False when it is not newer than the last accepted one."""
        if self.mfa_last_step is not None and step <= self.mfa_last_step:
            return False
        self.mfa_last_step = step
        return True
