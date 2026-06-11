"""SQLAlchemy repository for the global failed-login throttle (not tenant-scoped)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from medicore.application.common.login_throttle import WINDOW_MINUTES, lockout_until
from medicore.infrastructure.persistence.models.login_attempt import LoginAttemptModel


class SqlLoginThrottleRepository:
    """Each method commits its own short transaction: the recorded failure must survive
    the ``AuthenticationFailed`` raised right after it."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def locked_until(self, identifier: str, now: datetime) -> datetime | None:
        row = self._s.get(LoginAttemptModel, identifier)
        if row is None or row.locked_until is None or row.locked_until <= now:
            return None
        return row.locked_until

    def record_failure(self, identifier: str, now: datetime) -> datetime | None:
        # Single atomic UPSERT so concurrent attempts across N workers never lose a
        # count; a failure older than the window restarts the count instead of
        # accumulating forever.
        count = self._s.execute(
            text(
                """
                INSERT INTO login_attempts (identifier, failed_count, last_failed_at)
                VALUES (:id, 1, :now)
                ON CONFLICT (identifier) DO UPDATE SET
                    failed_count = CASE
                        WHEN login_attempts.last_failed_at < :window_start THEN 1
                        ELSE login_attempts.failed_count + 1
                    END,
                    last_failed_at = :now
                RETURNING failed_count
                """
            ),
            {
                "id": identifier,
                "now": now,
                "window_start": now - timedelta(minutes=WINDOW_MINUTES),
            },
        ).scalar_one()
        locked = lockout_until(count, now)
        if locked is not None:
            self._s.execute(
                text("UPDATE login_attempts SET locked_until = :lu WHERE identifier = :id"),
                {"lu": locked, "id": identifier},
            )
        self._s.commit()
        return locked

    def reset(self, identifier: str) -> None:
        self._s.query(LoginAttemptModel).filter(
            LoginAttemptModel.identifier == identifier
        ).delete()
        self._s.commit()
