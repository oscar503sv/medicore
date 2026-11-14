"""Delete the session rows that can no longer authenticate (expired or revoked).

Usage (scheduled daily, in every environment):
    .venv/bin/python scripts/purge_expired_sessions.py

Covers clinic, console and second-step challenge rows. Its outcome is recorded for the
console's Monitoring page, so a failed or missing run shows up there.
"""

from __future__ import annotations

from medicore.application.use_cases.monitoring import RecordJobRun
from medicore.application.use_cases.sessions import PurgeExpiredSessions
from medicore.infrastructure.auth.system_clock import SystemClock
from medicore.infrastructure.database.engine import get_session_factory
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory

JOB = "session_purge"


def main() -> None:
    clock = SystemClock()
    factory = SqlAlchemyUnitOfWorkFactory(get_session_factory())
    started = clock.now()
    jobs = RecordJobRun(factory, clock)
    try:
        deleted = PurgeExpiredSessions(factory, clock).execute()
    except BaseException as exc:
        jobs.execute(JOB, started, ok=False, detail=type(exc).__name__)
        raise
    jobs.execute(JOB, started, ok=True, detail=f"{deleted} sessions deleted")
    print(f"{deleted} sessions deleted")


if __name__ == "__main__":
    main()
