"""Platform console · Monitoring: system status, recorded server errors, readiness."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.ports.runtime import RuntimeFacts
from medicore.application.use_cases.monitoring import (
    ERROR_RETENTION_DAYS,
    CheckReadiness,
    GetSystemStatus,
    ListServerErrors,
    RecordServerError,
    RecordServerErrorCommand,
)
from medicore.application.use_cases.platform import ImpersonateTenant
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.shared.identifiers import AuditLogId, SessionId
from tests.support.builders import seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock

NOW = datetime(2026, 5, 31, 9, 0)


class StaticRuntime:
    def facts(self) -> RuntimeFacts:
        return RuntimeFacts(
            version="0.1.0", commit="abc1234", environment="test", python="3.12.0",
            started_at=NOW - timedelta(hours=2),
        )


def _actor(seed) -> PlatformActorContext:
    return PlatformActorContext(admin_id=seed.platform_admin.id)


def _status(seed):
    return GetSystemStatus(seed.factory, FixedClock(NOW), StaticRuntime()).execute(_actor(seed))


def _session(seed, *, scope="tenant", impersonator=None, expires=NOW + timedelta(hours=1),
             revoked=None):
    s = AuthSession(
        id=SessionId.new(), scope=scope,
        user_id=seed.admin.id.value if scope == "tenant" else seed.platform_admin.id.value,
        created_at=NOW - timedelta(minutes=5), expires_at=expires,
        tenant_id=seed.tenant.id if scope == "tenant" else None, revoked_at=revoked,
        impersonator_id=impersonator,
    )
    seed.factory.store.sessions[s.id.value] = s
    return s


def _error(seed, when: datetime, route="/api/v1/patients", location="use_cases/patients.py:10"):
    e = ErrorEvent(
        id=uuid.uuid4(), occurred_at=when, method="GET", route=route, status=500,
        error_type="RuntimeError", location=location,
    )
    seed.factory.store.error_events[e.id] = e
    return e


def test_status_reports_runtime_and_database():
    seed = seed_clinic()
    dto = _status(seed)
    assert dto.runtime.commit == "abc1234"
    assert dto.uptime_seconds == 2 * 3600
    assert dto.database.revision == "head"
    assert dto.database_latency_ms >= 0


def test_sessions_are_counted_by_kind_and_support_access_is_listed():
    seed = seed_clinic()
    _session(seed)
    _session(seed, scope="platform")
    support = _session(seed, impersonator=seed.platform_admin.id.value)
    _session(seed, expires=NOW - timedelta(minutes=1))  # expired
    _session(seed, revoked=NOW - timedelta(minutes=1))  # revoked

    dto = _status(seed)

    assert dto.sessions == {"tenant": 1, "support": 1, "platform": 1}
    [open_support] = dto.impersonations
    assert open_support.session_id == str(support.id)
    assert open_support.admin_name == seed.platform_admin.name
    assert open_support.clinic_name == seed.tenant.legal_name


def test_impersonation_marks_the_session_with_the_superadmin():
    seed = seed_clinic()
    ImpersonateTenant(seed.factory, FakeTokenIssuer(), FixedClock(NOW)).execute(
        _actor(seed), seed.tenant.id, reason="ticket 12"
    )
    [session] = seed.factory.store.sessions.values()
    assert session.impersonator_id == seed.platform_admin.id.value
    assert _status(seed).sessions["support"] == 1


def test_login_pressure_counts_recent_failures_and_lists_active_lockouts():
    seed = seed_clinic()
    attempts = seed.factory.store.login_attempts
    attempts["tenant:clinica-norte:ana@x.test"] = (6, NOW - timedelta(minutes=1),
                                                   NOW + timedelta(minutes=2))
    attempts["platform:root@x.test"] = (2, NOW - timedelta(hours=3), None)
    attempts["tenant:clinica-norte:old@x.test"] = (3, NOW - timedelta(days=2), None)
    seed.factory.store.audit[uuid.uuid4()] = AuditLog(
        id=AuditLogId.new(), tenant_id=seed.tenant.id, actor_id=seed.admin.id,
        action="auth.login_locked", entity_type="User", entity_id=str(seed.admin.id),
        timestamp=NOW - timedelta(hours=1),
    )

    dto = _status(seed)

    assert dto.logins.failing_accounts == 2
    assert dto.logins.failed_attempts == 8
    [locked] = dto.logins.locked
    assert (locked.scope, locked.clinic_slug, locked.email) == (
        "tenant", "clinica-norte", "ana@x.test"
    )
    assert dto.lockouts_24h == 1


def test_errors_are_counted_and_grouped():
    seed = seed_clinic()
    _error(seed, NOW - timedelta(hours=1))
    _error(seed, NOW - timedelta(hours=2))
    _error(seed, NOW - timedelta(days=3), route="/api/v1/records", location="x.py:1")
    _error(seed, NOW - timedelta(days=9))  # outside the 7-day window

    dto = _status(seed)

    assert (dto.errors_24h, dto.errors_7d) == (2, 3)
    top = dto.error_groups[0]
    assert (top.route, top.count, top.last_at) == (
        "/api/v1/patients", 2, NOW - timedelta(hours=1)
    )
    assert len(dto.error_groups) == 2


def test_record_server_error_keeps_it_and_purges_past_retention():
    seed = seed_clinic()
    stale = _error(seed, NOW - timedelta(days=ERROR_RETENTION_DAYS + 1))
    kept = _error(seed, NOW - timedelta(days=ERROR_RETENTION_DAYS - 1))

    event = RecordServerError(seed.factory, FixedClock(NOW)).execute(
        RecordServerErrorCommand(
            method="post", route="/api/v1/consultations/{consultation_id}/sign", status=500,
            error_type="sqlalchemy.exc.OperationalError", location="x" * 400,
        )
    )

    store = seed.factory.store.error_events
    assert set(store) == {kept.id, event.id}
    assert stale.id not in store
    assert event.method == "POST" and event.occurred_at == NOW
    assert len(event.location) == 300


def test_list_server_errors_newest_first_with_paging():
    seed = seed_clinic()
    for hours in (3, 1, 2):
        _error(seed, NOW - timedelta(hours=hours))
    page = ListServerErrors(seed.factory).execute(_actor(seed), limit=2, offset=0)
    assert page.total == 3
    assert [e.occurred_at for e in page.items] == [
        NOW - timedelta(hours=1), NOW - timedelta(hours=2)
    ]
    assert ListServerErrors(seed.factory).execute(_actor(seed), limit=1000).limit == 100


def test_readiness_fails_when_the_database_is_down():
    seed = seed_clinic()
    CheckReadiness(seed.factory).execute()
    seed.factory.store.database_down = True
    with pytest.raises(ConnectionError):
        CheckReadiness(seed.factory).execute()
