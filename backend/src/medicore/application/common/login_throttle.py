"""Login throttling policy: failed-attempt counting with temporary lockout.

Pure functions shared by the SQL and in-memory throttle repositories so the backoff
rules live in one place and stay unit-testable without a database.
"""

from __future__ import annotations

from datetime import datetime, timedelta

MAX_ATTEMPTS = 5  # consecutive failures allowed before the lockout engages
WINDOW_MINUTES = 15  # a failure older than this restarts the count
MAX_LOCKOUT_MINUTES = 15  # backoff cap


def tenant_login_identifier(slug: str, email: str) -> str:
    return f"tenant:{slug.strip().lower()}:{email.strip().lower()}"


def platform_login_identifier(email: str) -> str:
    return f"platform:{email.strip().lower()}"


def lockout_until(failed_count: int, now: datetime) -> datetime | None:
    """Lockout deadline after the Nth consecutive failure (None below the threshold).

    Exponential backoff: 1 min on the 5th failure, doubling per extra failure, capped at
    15 min. Applied to existing and non-existing accounts alike so the response does not
    reveal whether an account exists.
    """
    if failed_count < MAX_ATTEMPTS:
        return None
    minutes = min(2 ** (failed_count - MAX_ATTEMPTS), MAX_LOCKOUT_MINUTES)
    return now + timedelta(minutes=minutes)
