"""Platform console · Monitoring: is the system healthy right now?

The process and its deploy (version, commit, uptime), the database (reachable, latency,
size, applied migration, largest tables), sign-in pressure (failing accounts, active
lockouts), live sessions including support access, and the unexpected server errors of
the last days. Business numbers live in ``business.py``.

Recorded errors keep no message or request data (see ``ErrorEvent``) and are purged after
``ERROR_RETENTION_DAYS``.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from medicore.application.common.context import PlatformActorContext
from medicore.application.ports.clock import Clock
from medicore.application.ports.runtime import RuntimeFacts, RuntimeInfo
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.repositories._support import (
    ActiveImpersonation,
    DatabaseStatus,
    ErrorGroup,
    LoginPressure,
    Page,
    TableSize,
)

ERROR_RETENTION_DAYS = 30
LOGIN_WINDOW_HOURS = 24
ERROR_GROUP_DAYS = 7
TOP_TABLES = 8
TOP_ERROR_GROUPS = 10
MAX_PAGE = 100


@dataclass(frozen=True, slots=True)
class SystemStatusDTO:
    now: datetime
    runtime: RuntimeFacts
    uptime_seconds: int
    database: DatabaseStatus
    database_latency_ms: float
    largest_tables: list[TableSize]
    logins: LoginPressure
    lockouts_24h: int
    sessions: dict[str, int]
    impersonations: list[ActiveImpersonation]
    errors_24h: int
    errors_7d: int
    error_groups: list[ErrorGroup] = field(default_factory=list)


class GetSystemStatus:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, runtime: RuntimeInfo) -> None:
        self._factory = uow_factory
        self._clock = clock
        self._runtime = runtime

    def execute(self, actor: PlatformActorContext) -> SystemStatusDTO:
        now = self._clock.now()
        day_ago = now - timedelta(hours=LOGIN_WINDOW_HOURS)
        week_ago = now - timedelta(days=ERROR_GROUP_DAYS)
        facts = self._runtime.facts()
        with self._factory.monitoring_reads() as reads:
            started = time.perf_counter()
            reads.ping()
            latency = (time.perf_counter() - started) * 1000
            return SystemStatusDTO(
                now=now,
                runtime=facts,
                uptime_seconds=max(0, int((now - facts.started_at).total_seconds())),
                database=reads.database(),
                database_latency_ms=round(latency, 1),
                largest_tables=reads.largest_tables(TOP_TABLES),
                logins=reads.login_pressure(day_ago, now),
                lockouts_24h=reads.lockouts_since(day_ago),
                sessions=reads.sessions_by_kind(now),
                impersonations=reads.active_impersonations(now),
                errors_24h=reads.errors_since(day_ago),
                errors_7d=reads.errors_since(week_ago),
                error_groups=reads.error_groups(week_ago, TOP_ERROR_GROUPS),
            )


class ListServerErrors:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(
        self, actor: PlatformActorContext, limit: int = 50, offset: int = 0
    ) -> Page[ErrorEvent]:
        with self._factory.monitoring_reads() as reads:
            return reads.recent_errors(min(max(limit, 1), MAX_PAGE), max(offset, 0))


class CheckReadiness:
    """Readiness probe: the API can serve requests only if the database answers."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self) -> None:
        with self._factory.monitoring_reads() as reads:
            reads.ping()


@dataclass(frozen=True, slots=True)
class RecordServerErrorCommand:
    method: str
    route: str
    status: int
    error_type: str
    location: str


class RecordServerError:
    """Keep one unexpected error for the console and drop the ones past retention."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, cmd: RecordServerErrorCommand) -> ErrorEvent:
        now = self._clock.now()
        event = ErrorEvent(
            id=uuid.uuid4(),
            occurred_at=now,
            method=cmd.method.upper()[:10],
            route=cmd.route[:300],
            status=cmd.status,
            error_type=cmd.error_type[:200],
            location=cmd.location[:300],
        )
        with self._factory.error_log() as log:
            log.record(event)
            log.purge_before(now - timedelta(days=ERROR_RETENTION_DAYS))
        return event
