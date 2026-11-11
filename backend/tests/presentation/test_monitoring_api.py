"""Platform console · Monitoring endpoints, the readiness probe and 500 recording."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from medicore.application.ports.runtime import RuntimeFacts
from medicore.presentation.dependencies import get_runtime
from medicore.presentation.error_handlers import describe_exception
from tests.support.builders import PASSWORD


class StaticRuntime:
    def facts(self) -> RuntimeFacts:
        # Naive like the tests' FixedClock (2026-05-31 09:00).
        return RuntimeFacts("0.1.0", None, "test", "3.12", datetime(2026, 5, 31, 8, 0))


def test_system_status_endpoint(client, platform_headers):
    client.app.dependency_overrides[get_runtime] = StaticRuntime
    resp = client.get("/api/v1/platform/monitoring", headers=platform_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["database"]["revision"] == "head"
    assert data["runtime"]["uptime_seconds"] == 3600
    assert data["errors"]["retention_days"] == 30
    assert set(data["sessions"]) == {"tenant", "support", "platform"}
    assert data["sessions"]["platform"] == 1  # this very console session
    assert len(data["errors"]["daily"]) == 30
    assert data["database"]["connections"]["max_connections"] == 100
    assert data["jobs"][0]["job"] == "demo_reset"
    assert data["jobs"][0]["state"] == "never"
    assert data["jobs"][0]["expected_every_hours"] == 26
    [login] = data["logins"]["console"]  # the console sign-in of this test
    assert login["action"] == "auth.platform_login"


def test_monitoring_needs_a_platform_session(client, admin_headers):
    assert client.get("/api/v1/platform/monitoring", headers=admin_headers).status_code == 401
    assert (
        client.get("/api/v1/platform/monitoring/errors", headers=admin_headers).status_code
        == 401
    )


def test_readiness_probe(seed, client):
    assert client.get("/health/ready").json() == {"status": "ok", "database": "ok"}
    assert client.get("/api/v1/health/ready").status_code == 200  # reachable through nginx
    seed.factory.store.database_down = True
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["database"] == "down"


def test_unhandled_error_is_recorded_without_its_message(seed, client, platform_headers):
    app = client.app

    @app.get("/api/v1/boom/{patient_id}")
    def boom(patient_id: str):
        raise RuntimeError(f"secret patient detail {patient_id}")

    lenient = TestClient(app, raise_server_exceptions=False)
    assert lenient.get("/api/v1/boom/123").status_code == 500

    resp = client.get("/api/v1/platform/monitoring/errors", headers=platform_headers)
    assert resp.status_code == 200, resp.text
    [event] = resp.json()["items"]
    assert event["route"] == "/api/v1/boom/{patient_id}"
    assert event["method"] == "GET" and event["error_type"] == "RuntimeError"
    assert "test_monitoring_api.py" in event["location"]
    assert "secret" not in str(event)


def test_describe_exception_points_at_the_innermost_project_frame():
    def inner():
        raise KeyError("dni 01234567-8")

    try:
        inner()
    except KeyError as exc:
        kind, location = describe_exception(exc)
    assert kind == "KeyError"
    assert location.endswith("in inner")
    assert "01234567" not in location


def test_platform_login_records_where_the_session_comes_from(seed, client):
    resp = client.post(
        "/api/v1/platform/login",
        json={"email": seed.platform_admin.email, "password": PASSWORD},
        headers={"User-Agent": "Firefox/140"},
    )
    assert resp.status_code == 200, resp.text
    [session] = seed.factory.store.sessions.values()
    assert session.scope == "platform"
    assert session.user_agent == "Firefox/140"
    assert session.ip_address


def test_api_requests_are_measured_per_route_template(seed, client, platform_headers):
    client.app.state.request_recorder.flush_every = 0  # flush after every request
    client.app.dependency_overrides[get_runtime] = StaticRuntime
    client.get("/api/v1/platform/tenants", headers=platform_headers)
    client.get(f"/api/v1/platform/tenants/{seed.tenant.id}", headers=platform_headers)
    client.get("/api/v1/does-not-exist", headers=platform_headers)
    client.get("/health/ready")  # probes are not measured

    stats = seed.factory.store.request_stats.values()
    routes = {(r.method, r.route): r for r in stats}
    assert ("GET", "/api/v1/platform/tenants/{tenant_id}") in routes
    assert ("GET", "(unmatched)") in routes
    assert routes[("GET", "(unmatched)")].client_errors == 1
    assert not any("health" in r.route for r in stats)

    perf = client.get("/api/v1/platform/monitoring", headers=platform_headers).json()[
        "performance"
    ]
    assert perf["requests"] >= 4  # the platform login and the calls above
    assert len(perf["hourly"]) == 24
    assert perf["p95_ms"] is not None
