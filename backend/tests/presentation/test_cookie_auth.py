"""API tests: cookie-based sessions (httpOnly JWT + double-submit CSRF).

The Bearer header path is covered by every other presentation test; here we exercise the
cookie path: login sets the cookies, safe requests ride on them, mutations additionally
require the X-CSRF-Token header, and logout clears everything.
"""

from __future__ import annotations

from tests.support.builders import PASSWORD


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
        assert client.cookies.get("mc_platform")
        assert client.get("/api/v1/platform/tenants").status_code == 200

    def test_platform_cookie_does_not_open_tenant_endpoints(self, seed, client):
        _platform_login(seed, client)
        # mc_platform is not mc_session: tenant endpoints see no credential at all.
        assert client.get("/api/v1/patients").status_code == 401

    def test_platform_logout_clears_the_session(self, seed, client):
        _platform_login(seed, client)
        assert client.post("/api/v1/platform/logout").status_code == 204
        assert client.get("/api/v1/platform/tenants").status_code == 401

    def test_impersonation_sets_tenant_cookie(self, seed, client):
        _platform_login(seed, client)
        csrf = client.cookies.get("mc_csrf")
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
