"""API tests: timezone stays with support, the console opens sites, and a delegated
``users.manage`` has limits (no doctors or admins, no own account)."""

from __future__ import annotations

import pytest

from medicore.application.common.permissions import Permission, permissions_for
from medicore.domain.enums import Role
from tests.support.builders import PASSWORD


def test_clinic_cannot_change_its_timezone(client, admin_headers):
    resp = client.patch(
        "/api/v1/organization", json={"timezone": "America/El_Salvador"}, headers=admin_headers
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "organization.timezone_locked"


def test_console_opens_a_site(seed, client, platform_headers):
    resp = client.post(
        f"/api/v1/platform/tenants/{seed.tenant.id}/locations",
        json={"name": "Sede Norte", "address": "Calle 1"},
        headers=platform_headers,
    )
    assert resp.status_code == 201, resp.text
    assert "Sede Norte" in [loc["name"] for loc in resp.json()["locations"]]


def test_console_route_needs_a_platform_session(seed, client, admin_headers):
    resp = client.post(
        f"/api/v1/platform/tenants/{seed.tenant.id}/locations",
        json={"name": "Sede Norte"},
        headers=admin_headers,
    )
    assert resp.status_code == 401


@pytest.fixture
def delegate_headers(client, admin_headers, receptionist_headers):
    """The receptionist, handed users.view and users.manage by the admin. Requested after
    the grant so the session resolves the new set."""
    perms = {str(p) for p in permissions_for(Role.RECEPTIONIST)}
    perms |= {str(Permission.USERS_VIEW), str(Permission.USERS_MANAGE)}
    resp = client.put(
        "/api/v1/permissions/roles/receptionist",
        json={"permissions": sorted(perms)},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    return receptionist_headers


def test_delegate_cannot_promote_themselves_to_doctor(seed, client, delegate_headers):
    resp = client.put(
        f"/api/v1/users/{seed.receptionist.id}/role",
        json={"role": "doctor"},
        headers=delegate_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "users.self_management"
    me = client.get("/api/v1/auth/me", headers=delegate_headers)
    assert me.json()["role"] == "receptionist"


def test_delegate_cannot_create_a_doctor(client, delegate_headers):
    resp = client.post(
        "/api/v1/users",
        json={
            "name": "Dr. Nuevo", "email": "nuevo@clinica-norte.test", "role": "doctor",
            "password": "Secreto-Seguro-123",
        },
        headers=delegate_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "users.doctor_admin_only"


def test_delegate_cannot_reset_a_doctors_password(seed, client, delegate_headers):
    resp = client.post(
        f"/api/v1/users/{seed.doctor.id}/reset-password",
        json={"password": "Takeover-Clave-123"},
        headers=delegate_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "users.doctor_admin_only"
    login = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    assert login.status_code == 200


def test_delegate_still_manages_a_nurse(seed, client, delegate_headers):
    resp = client.patch(
        f"/api/v1/users/{seed.nurse.id}", json={"name": "Ana Pérez"}, headers=delegate_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Ana Pérez"


def test_admin_cannot_suspend_themselves(seed, client, admin_headers):
    resp = client.post(f"/api/v1/users/{seed.admin.id}/suspend", headers=admin_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "users.self_management"
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 200
