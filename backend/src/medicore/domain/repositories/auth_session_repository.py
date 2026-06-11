"""AuthSessionRepository port — the global, revocable session store (not tenant-scoped)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.shared.identifiers import SessionId


class AuthSessionRepository(Protocol):
    def get(self, session_id: SessionId) -> AuthSession | None: ...

    def add(self, session: AuthSession) -> None: ...

    def revoke(self, session_id: SessionId, now: datetime) -> None: ...

    def revoke_all_for_user(
        self, user_id: UUID, now: datetime, except_id: SessionId | None = None
    ) -> None:
        """Revoke every active session of the user, optionally sparing the current one."""
        ...

    def delete_expired_for_user(self, user_id: UUID, now: datetime) -> None:
        """Opportunistic cleanup on login, so expired rows never need a cron job."""
        ...
