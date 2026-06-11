"""AuthSession — a revocable server-side login session.

Every issued JWT references one of these rows via its ``sid`` claim; a token whose
session is revoked, expired or missing is rejected, which makes logout, password
changes and account suspension take effect immediately instead of waiting for the
token to expire.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from medicore.domain.shared.identifiers import SessionId, TenantId


@dataclass(slots=True)
class AuthSession:
    id: SessionId
    scope: str  # "tenant" | "platform"
    # User.id for tenant sessions, PlatformAdmin.id for platform sessions — kept as a
    # plain UUID because the session store spans both account kinds.
    user_id: UUID
    created_at: datetime
    expires_at: datetime
    tenant_id: TenantId | None = None  # None for platform sessions
    revoked_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
