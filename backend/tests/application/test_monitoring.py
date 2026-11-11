"""Platform console · Monitoring: system status, recorded server errors, readiness."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import AuthenticationFailed, TooManyLoginAttempts
from medicore.application.ports.runtime import RuntimeFacts
from medicore.application.use_cases.monitoring import (
    ERROR_RETENTION_DAYS,
    ERROR_TREND_DAYS,
    JOB_RETENTION_DAYS,
    CheckReadiness,
    GetSystemStatus,
    ListServerErrors,
    RecordJobRun,
    RecordServerError,
    RecordServerErrorCommand,
)
from medicore.application.use_cases.platform import AuthenticatePlatformAdmin, ImpersonateTenant
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.entities.job_run import JobRun
from medicore.domain.shared.identifiers import AuditLogId, SessionId
from tests.support.builders import PASSWORD, seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock, PlainPasswordHasher

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


def _error(seed, when: datetime, route="/api/v1/patients", location="use_cases/patients.py:10",
           commit=None):
    e = ErrorEvent(
        id=uuid.uuid4(), occurred_at=when, method="GET", route=route, status=500,
        error_type="RuntimeError", location=location, commit=commit,
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

    event = RecordServerError(seed.factory, FixedClock(NOW), StaticRuntime()).execute(
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
    assert event.commit == "abc1234"  # tagged with the running deploy


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


def test_error_groups_tell_the_deploys_apart_and_the_trend_is_zero_filled():
    seed = seed_clinic()
    _error(seed, NOW - timedelta(days=2), commit="old1111")
    _error(seed, NOW - timedelta(hours=1), commit="abc1234")

    dto = _status(seed)

    [group] = dto.error_groups
    assert (group.first_commit, group.last_commit) == ("old1111", "abc1234")
    assert group.first_at == NOW - timedelta(days=2)
    assert len(dto.errors_daily) == ERROR_TREND_DAYS
    assert dto.errors_daily[-1] == (NOW.date(), 1)
    assert dto.errors_daily[-3] == ((NOW - timedelta(days=2)).date(), 1)
    assert sum(n for _, n in dto.errors_daily) == 2


def _run(seed, job, finished, ok=True):
    run = JobRun(id=uuid.uuid4(), job=job, started_at=finished - timedelta(minutes=1),
                 finished_at=finished, ok=ok, detail="")
    seed.factory.store.job_runs[run.id] = run


def _jobs(seed):
    return {j.job: j.state for j in _status(seed).jobs}


def test_scheduled_jobs_states():
    seed = seed_clinic()
    assert _jobs(seed) == {"demo_reset": "never"}

    _run(seed, "demo_reset", NOW - timedelta(hours=3))
    assert _jobs(seed)["demo_reset"] == "ok"

    _run(seed, "demo_reset", NOW - timedelta(hours=1), ok=False)
    assert _jobs(seed)["demo_reset"] == "failed"

    seed.factory.store.job_runs.clear()
    _run(seed, "demo_reset", NOW - timedelta(hours=30))
    _run(seed, "demo_seed", NOW - timedelta(days=10))  # ad-hoc task: no schedule, still listed
    assert _jobs(seed) == {"demo_reset": "overdue", "demo_seed": "ok"}


def test_record_job_run_purges_old_runs():
    seed = seed_clinic()
    _run(seed, "demo_reset", NOW - timedelta(days=JOB_RETENTION_DAYS + 1))
    run = RecordJobRun(seed.factory, FixedClock(NOW)).execute(
        "demo_reset", NOW - timedelta(minutes=2), ok=True, detail="2 clínicas"
    )
    assert list(seed.factory.store.job_runs) == [run.id]
    assert run.finished_at == NOW


def _login(seed, password, email=None):
    auth = AuthenticatePlatformAdmin(
        seed.factory, PlainPasswordHasher(), FakeTokenIssuer(), FixedClock(NOW)
    )
    return auth.execute(email or seed.platform_admin.email, password, "10.0.0.7", "Firefox/140")


def test_console_sign_ins_are_audited():
    seed = seed_clinic()
    _login(seed, PASSWORD)
    with pytest.raises(AuthenticationFailed):
        _login(seed, "wrong-password")
    with pytest.raises(AuthenticationFailed):
        _login(seed, "wrong-password", email="nobody@medicore.test")  # no account: no entry

    logins = _status(seed).console_logins
    # Same instant (fixed clock), so compare without order.
    assert sorted(c.action for c in logins) == ["auth.platform_login", "auth.platform_login_failed"]
    assert {c.admin_name for c in logins} == {seed.platform_admin.name}
    assert all(c.ip_address == "10.0.0.7" for c in logins)


def test_console_lockout_is_audited_and_counted():
    seed = seed_clinic()
    for _ in range(5):
        with pytest.raises(AuthenticationFailed):
            _login(seed, "wrong-password")
    with pytest.raises(TooManyLoginAttempts):
        _login(seed, PASSWORD)

    dto = _status(seed)
    assert dto.lockouts_24h == 1
    actions = [c.action for c in dto.console_logins]
    assert actions.count("auth.platform_login_locked") == 1
    assert actions.count("auth.platform_login_failed") == 4
