"""API tests: auth endpoints."""

from __future__ import annotations

from medicore.application.common.permissions import permissions_for
from medicore.domain.enums import Role
from tests.support.builders import PASSWORD


def test_health(client):
    assert client.get("/health").status_code == 200


def test_login_success(seed, client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "doctor"
    assert data["name"] == seed.doctor.name
    assert data["timezone"] == seed.tenant.timezone
    # The token never travels in the body — it lives in the httpOnly session cookie.
    assert "token" not in data
    assert client.cookies.get("mc_session")
    assert client.cookies.get("mc_csrf")
    assert data["permissions"] == sorted(str(p) for p in permissions_for(Role.DOCTOR))


def test_login_wrong_password(seed, client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_org(seed, client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": "does-not-exist", "email": seed.doctor.email, "password": PASSWORD},
    )
    assert resp.status_code == 401


def test_login_lockout_returns_429_with_retry_after(seed, client):
    bad = {"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": "wrong"}
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json=bad).status_code == 401

    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/v1/patients")
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/v1/patients", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


def test_switch_theme(client, auth_headers):
    resp = client.post("/api/v1/auth/theme", json={"theme": "dark"}, headers=auth_headers)
    assert resp.status_code == 204


def test_get_my_profile(seed, client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["email"] == seed.doctor.email
    assert data["role"] == "doctor"
    assert data["specialty"] == seed.doctor.specialty
    assert data["bio"] is None
    assert data["permissions"] == sorted(str(p) for p in permissions_for(Role.DOCTOR))


def test_get_my_profile_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_update_my_profile(seed, client, auth_headers):
    resp = client.patch(
        "/api/v1/auth/me",
        json={"name": "Dra. Elena Vásquez", "phone": "+34 911 23 45 67", "bio": "12 años."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Dra. Elena Vásquez"
    assert data["phone"] == "+34 911 23 45 67"
    assert data["bio"] == "12 años."
    # email and specialty are not affected
    assert data["email"] == seed.doctor.email
    assert data["specialty"] == seed.doctor.specialty
