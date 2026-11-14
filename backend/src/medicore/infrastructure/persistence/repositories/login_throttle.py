"""SQLAlchemy repository for the global sign-in throttle (not tenant-scoped)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, text, update
from sqlalchemy.orm import Session

from medicore.application.common.login_throttle import (
    KNOWN_IP_TTL,
    WINDOW,
    Reservation,
    ThrottlePolicy,
)
from medicore.infrastructure.persistence.models.login_attempt import LoginAttemptModel


class SqlLoginThrottleRepository:
    """Each method commits its own short transaction: a reserved attempt must survive the
    ``AuthenticationFailed`` raised after it, and must not hold a row lock during bcrypt."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def reserve(self, identifier: str, policy: ThrottlePolicy, now: datetime) -> Reservation:
        # One atomic UPSERT that counts and answers, so N parallel attempts see N distinct
        # counts and never all slip under the threshold; an attempt older than the window
        # restarts the count. The conflict WHERE skips a locked identifier: a rejected
        # attempt is not counted.
        row = self._s.execute(
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
                WHERE login_attempts.locked_until IS NULL OR login_attempts.locked_until <= :now
                RETURNING failed_count, last_success_at
                """
            ),
            {"id": identifier, "now": now, "window_start": now - WINDOW},
        ).one_or_none()
        if row is None:
            locked_until, last_success_at = self._s.execute(
                text(
                    "SELECT locked_until, last_success_at FROM login_attempts "
                    "WHERE identifier = :id"
                ),
                {"id": identifier},
            ).one()
            self._s.commit()
            return Reservation(False, locked_until, last_success_at)
        count, last_success_at = row
        locked = policy.lockout_until(count, now)
        # Always written, even as NULL, to clear an expired lock. It runs in the UPSERT's
        # transaction, so the row lock is held until the commit and the next reservation
        # waits for it and then sees the lock.
        self._s.execute(
            text("UPDATE login_attempts SET locked_until = :lu WHERE identifier = :id"),
            {"lu": locked, "id": identifier},
        )
        self._s.commit()
        return Reservation(True, locked, last_success_at)

    def refund(self, identifier: str, policy: ThrottlePolicy) -> None:
        self._s.execute(
            text(
                """
                UPDATE login_attempts SET
                    failed_count = GREATEST(failed_count - 1, 0),
                    locked_until = CASE
                        WHEN failed_count - 1 < :max THEN NULL ELSE locked_until
                    END
                WHERE identifier = :id
                """
            ),
            {"id": identifier, "max": policy.max_attempts},
        )
        self._s.commit()

    def reset(self, identifier: str, now: datetime) -> None:
        self._s.execute(
            text(
                """
                UPDATE login_attempts SET
                    failed_count = 0, locked_until = NULL, last_success_at = :now
                WHERE identifier = :id
                """
            ),
            {"id": identifier, "now": now},
        )
        self._s.commit()

    def clear_account(self, account: str) -> None:
        self._s.execute(
            update(LoginAttemptModel)
            .where(
                or_(
                    LoginAttemptModel.identifier == account,
                    # "_" is common in emails and would otherwise match any character.
                    LoginAttemptModel.identifier.startswith(f"{account}|", autoescape=True),
                )
            )
            .values(failed_count=0, locked_until=None)
        )
        self._s.commit()

    def purge_stale(self, now: datetime) -> None:
        self._s.query(LoginAttemptModel).filter(
            LoginAttemptModel.last_failed_at < now - WINDOW,
            or_(LoginAttemptModel.locked_until.is_(None), LoginAttemptModel.locked_until <= now),
            or_(
                LoginAttemptModel.last_success_at.is_(None),
                LoginAttemptModel.last_success_at < now - KNOWN_IP_TTL,
            ),
        ).delete(synchronize_session=False)
        self._s.commit()
