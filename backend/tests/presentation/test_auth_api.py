"""API tests: auth endpoints."""

from __future__ import annotations

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
    assert "token" in data


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


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/v1/patients")
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/v1/patients", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401


def test_switch_theme(client, auth_headers):
    resp = client.post("/api/v1/auth/theme", json={"theme": "dark"}, headers=auth_headers)
    assert resp.status_code == 204
