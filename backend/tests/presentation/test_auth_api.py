"""API tests: auth endpoints."""

from __future__ import annotations

from datetime import datetime

from medicore.application.common.permissions import permissions_for
from medicore.application.ports.token_issuer import SessionClaims
from medicore.domain.enums import Role
from tests.support.builders import PASSWORD
from tests.support.fakes import FakeTokenIssuer


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


def test_token_without_session_claim_rejected(seed, client):
    # A structurally valid token lacking the sid claim (e.g. issued before the deploy)
    # must not authenticate.
    token = FakeTokenIssuer().issue(
        SessionClaims(
            user_id=str(seed.doctor.id), tenant_id=str(seed.tenant.id), role="doctor"
        )
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_logout_revokes_the_server_side_session(seed, client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    assert resp.status_code == 200
    token = client.cookies.get("mc_session")

    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.clear()
    # the old token is dead even though the JWT itself has not expired
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_list_and_revoke_my_sessions(seed, client):
    from tests.presentation.conftest import bearer_login

    payload = {"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD}
    other = bearer_login(client, "/api/v1/auth/login", payload)
    current = bearer_login(client, "/api/v1/auth/login", payload)

    items = client.get("/api/v1/auth/me/sessions", headers=current).json()["items"]
    assert len(items) == 2
    assert sum(1 for i in items if i["current"]) == 1

    remote = next(i for i in items if not i["current"])
    resp = client.delete(f"/api/v1/auth/me/sessions/{remote['id']}", headers=current)
    assert resp.status_code == 204
    # the revoked session can no longer authenticate; the current one still can
    assert client.get("/api/v1/auth/me", headers=other).status_code == 401
    items = client.get("/api/v1/auth/me/sessions", headers=current).json()["items"]
    assert len(items) == 1 and items[0]["current"]


def test_cannot_revoke_a_foreign_session(seed, client, auth_headers, admin_headers):
    admin_items = client.get("/api/v1/auth/me/sessions", headers=admin_headers).json()["items"]
    resp = client.delete(
        f"/api/v1/auth/me/sessions/{admin_items[0]['id']}", headers=auth_headers
    )
    assert resp.status_code == 404
    # the admin session is untouched
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 200


def test_revoked_session_rejected_even_with_valid_token(seed, client, auth_headers):
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200

    for session in seed.factory.store.sessions.values():
        session.revoke(datetime(2026, 5, 31, 9, 1))
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 401


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
