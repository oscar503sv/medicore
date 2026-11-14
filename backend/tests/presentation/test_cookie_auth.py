"""API tests: cookie-based sessions (httpOnly JWT + double-submit CSRF).

The Bearer header path is covered by every other presentation test; here we exercise the
cookie path: login sets the cookies, safe requests ride on them, mutations additionally
require the X-CSRF-Token header, and logout clears everything.
"""

from __future__ import annotations

from datetime import timedelta

from medicore.domain.enums import UserStatus
from tests.support.builders import PASSWORD

BACKGROUND = {"X-Background-Refresh": "1"}


def _login(seed, client, user=None):
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "slug": str(seed.tenant.slug),
            "email": (user or seed.doctor).email,
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp


def _platform_login(seed, client):
    resp = client.post(
        "/api/v1/platform/login",
        json={"email": seed.platform_admin.email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp


class TestTenantCookies:
    def test_login_sets_httponly_session_cookie_and_no_token_in_body(self, seed, client):
        resp = _login(seed, client)
        assert "token" not in resp.json()
        set_cookie = ";".join(resp.headers.get_list("set-cookie"))
        assert "mc_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert client.cookies.get("mc_csrf")

    def test_get_authenticated_by_cookie(self, seed, client):
        _login(seed, client)
        resp = client.get("/api/v1/patients")  # no Authorization header
        assert resp.status_code == 200

    def test_cookie_mutation_without_csrf_header_is_403(self, seed, client):
        _login(seed, client)
        resp = client.post("/api/v1/auth/theme", json={"theme": "dark"})
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["detail"]

    def test_cookie_mutation_with_wrong_csrf_header_is_403(self, seed, client):
        _login(seed, client)
        resp = client.post(
            "/api/v1/auth/theme", json={"theme": "dark"}, headers={"X-CSRF-Token": "forged"}
        )
        assert resp.status_code == 403

    def test_cookie_mutation_with_csrf_header_succeeds(self, seed, client):
        _login(seed, client)
        csrf = client.cookies.get("mc_csrf")
        resp = client.post(
            "/api/v1/auth/theme", json={"theme": "dark"}, headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 204

    def test_bearer_mutation_needs_no_csrf(self, seed, client, auth_headers):
        # The browser never attaches the Authorization header on its own → no CSRF risk.
        resp = client.post("/api/v1/auth/theme", json={"theme": "dark"}, headers=auth_headers)
        assert resp.status_code == 204

    def test_logout_clears_the_session(self, seed, client):
        _login(seed, client)
        assert client.get("/api/v1/patients").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/patients").status_code == 401


class TestPlatformCookies:
    def test_platform_login_sets_its_own_cookie(self, seed, client):
        resp = _platform_login(seed, client)
        assert "token" not in resp.json()
        assert client.cookies.get("mc_console")
        assert client.cookies.get("mc_console_csrf")
        assert client.get("/api/v1/platform/tenants").status_code == 200

    def test_platform_cookie_does_not_open_tenant_endpoints(self, seed, client):
        _platform_login(seed, client)
        # mc_console is not mc_session: tenant endpoints see no credential at all.
        assert client.get("/api/v1/patients").status_code == 401

    def test_platform_logout_clears_the_session(self, seed, client):
        _platform_login(seed, client)
        assert client.post("/api/v1/platform/logout").status_code == 204
        assert client.get("/api/v1/platform/tenants").status_code == 401

    def test_platform_logout_revokes_the_server_side_session(self, seed, client):
        _platform_login(seed, client)
        token = client.cookies.get("mc_console")
        assert client.post("/api/v1/platform/logout").status_code == 204
        client.cookies.clear()
        # the old token is dead even though the JWT itself has not expired
        resp = client.get(
            "/api/v1/platform/tenants", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401

    def test_impersonation_sets_tenant_cookie(self, seed, client):
        _platform_login(seed, client)
        csrf = client.cookies.get("mc_console_csrf")
        resp = client.post(
            f"/api/v1/platform/tenants/{seed.tenant.id}/impersonate",
            json={"reason": "soporte: revisión de agenda"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        assert "token" not in resp.json()
        # The support session is a tenant session: the clinic app now works by cookie.
        assert client.cookies.get("mc_session")
        assert client.get("/api/v1/patients").status_code == 200

    def test_platform_cookie_is_path_scoped_and_strict(self, seed, client):
        resp = _platform_login(seed, client)
        cookies = {c.split("=", 1)[0]: c for c in resp.headers.get_list("set-cookie")}
        session_cookie = cookies["mc_console"]
        assert "Path=/api/v1/platform" in session_cookie
        assert "HttpOnly" in session_cookie
        assert "SameSite=strict" in session_cookie
        assert "Max-Age=28800" in session_cookie  # 8 h absolute cap
        csrf_cookie = cookies["mc_console_csrf"]
        # Path=/ so the SPA can read it from any page; HttpOnly would hide it from the SPA.
        assert "Path=/;" in csrf_cookie
        assert "HttpOnly" not in csrf_cookie
        assert "SameSite=strict" in csrf_cookie

    def test_clinic_logout_keeps_console_session(self, seed, client):
        _platform_login(seed, client)
        _login(seed, client)
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/patients").status_code == 401
        assert client.get("/api/v1/platform/tenants").status_code == 200

    def test_clinic_csrf_rejected_on_platform(self, seed, client):
        _platform_login(seed, client)
        _login(seed, client)
        clinic_csrf = client.cookies.get("mc_csrf")
        resp = client.post(
            f"/api/v1/platform/tenants/{seed.tenant.id}/impersonate",
            json={"reason": "soporte: revisión de agenda"},
            headers={"X-CSRF-Token": clinic_csrf},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "auth.csrf_invalid"

    def test_console_csrf_rejected_on_clinic(self, seed, client):
        _platform_login(seed, client)
        _login(seed, client)
        console_csrf = client.cookies.get("mc_console_csrf")
        resp = client.post(
            "/api/v1/auth/theme", json={"theme": "dark"}, headers={"X-CSRF-Token": console_csrf}
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "auth.csrf_invalid"

    def test_csrf_cookie_value_forged_but_equal_header_rejected(self, seed, client):
        _login(seed, client)
        client.cookies.delete("mc_csrf")
        client.cookies.set("mc_csrf", "forged")
        resp = client.post(
            "/api/v1/auth/theme", json={"theme": "dark"}, headers={"X-CSRF-Token": "forged"}
        )
        assert resp.status_code == 403

    def test_console_csrf_cookie_value_forged_but_equal_header_rejected(self, seed, client):
        _platform_login(seed, client)
        client.cookies.delete("mc_console_csrf")
        client.cookies.set("mc_console_csrf", "forged")
        resp = client.post(
            f"/api/v1/platform/tenants/{seed.tenant.id}/impersonate",
            json={"reason": "soporte: revisión de agenda"},
            headers={"X-CSRF-Token": "forged"},
        )
        assert resp.status_code == 403

    def test_idle_timeout_returns_401_code(self, seed, client, clock):
        _platform_login(seed, client)
        clock.set(clock.now() + timedelta(minutes=31))
        resp = client.get("/api/v1/platform/tenants")
        assert resp.status_code == 401
        assert resp.json()["code"] == "auth.session_idle_timeout"
        # the session was revoked, not just refused once
        clock.set(clock.now() - timedelta(minutes=30))
        assert client.get("/api/v1/platform/tenants").status_code == 401

    def test_foreground_request_extends_the_session(self, seed, client, clock):
        _platform_login(seed, client)
        for _ in range(3):
            clock.set(clock.now() + timedelta(minutes=20))
            assert client.get("/api/v1/platform/tenants").status_code == 200

    def test_background_header_does_not_extend(self, seed, client, clock):
        _platform_login(seed, client)
        clock.set(clock.now() + timedelta(minutes=20))
        assert client.get("/api/v1/platform/tenants", headers=BACKGROUND).status_code == 200
        clock.set(clock.now() + timedelta(minutes=11))
        resp = client.get("/api/v1/platform/tenants")
        assert resp.status_code == 401
        assert resp.json()["code"] == "auth.session_idle_timeout"

    def test_inactive_admin_rejected_on_next_request(self, seed, client):
        _platform_login(seed, client)
        assert client.get("/api/v1/platform/tenants").status_code == 200
        # the store hands out copies after a transaction snapshot, so edit the stored row
        seed.factory.store.platform_admins[seed.platform_admin.id.value].status = (
            UserStatus.SUSPENDED
        )
        resp = client.get("/api/v1/platform/tenants")
        assert resp.status_code == 401
        assert resp.json()["code"] == "auth.account_inactive"

    def test_logout_deletes_legacy_platform_cookie(self, seed, client):
        _platform_login(seed, client)
        client.cookies.set("mc_platform", "stale-token")
        resp = client.post("/api/v1/platform/logout")
        legacy = [c for c in resp.headers.get_list("set-cookie") if c.startswith("mc_platform=")]
        assert legacy
        assert "Max-Age=0" in legacy[0]
        assert "Path=/;" in legacy[0]
