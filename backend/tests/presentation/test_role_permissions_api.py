"""API tests: role-permission customization (tenant + platform endpoints)."""

from __future__ import annotations


def test_get_matrix_as_admin(client, admin_headers):
    resp = client.get("/api/v1/permissions", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "permissions.manage" in data["catalog"]
    assert data["roles"]["admin"]["customized"] is False
    assert data["roles"]["receptionist"]["effective"] == data["roles"]["receptionist"]["defaults"]


def test_get_matrix_forbidden_for_doctor(client, auth_headers):
    resp = client.get("/api/v1/permissions", headers=auth_headers)
    assert resp.status_code == 403


def test_update_and_reset_role(client, admin_headers):
    resp = client.put(
        "/api/v1/permissions/roles/receptionist",
        json={"permissions": ["patients.view", "diagnoses.view"]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()["roles"]["receptionist"]
    assert entry["customized"] is True
    assert entry["effective"] == ["diagnoses.view", "patients.view"]

    resp = client.delete("/api/v1/permissions/roles/receptionist", headers=admin_headers)
    assert resp.status_code == 200
    entry = resp.json()["roles"]["receptionist"]
    assert entry["customized"] is False


def test_update_admin_role_rejected(client, admin_headers):
    resp = client.put(
        "/api/v1/permissions/roles/admin", json={"permissions": []}, headers=admin_headers
    )
    assert resp.status_code == 400


def test_unknown_role_rejected(client, admin_headers):
    resp = client.put(
        "/api/v1/permissions/roles/superhero",
        json={"permissions": []},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_override_applies_to_requests(seed, client, admin_headers, receptionist_headers):
    """Revoking patients.view from receptionist turns their patient list into a 403."""
    assert client.get("/api/v1/patients", headers=receptionist_headers).status_code == 200
    resp = client.put(
        "/api/v1/permissions/roles/receptionist",
        json={"permissions": ["diagnoses.view"]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert client.get("/api/v1/patients", headers=receptionist_headers).status_code == 403


def test_platform_matrix_endpoints(seed, client, platform_headers):
    tenant_id = str(seed.tenant.id)
    resp = client.get(f"/api/v1/platform/tenants/{tenant_id}/permissions", headers=platform_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"]["nurse"]["customized"] is False

    resp = client.put(
        f"/api/v1/platform/tenants/{tenant_id}/permissions/roles/nurse",
        json={"permissions": ["patients.view"]},
        headers=platform_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"]["nurse"]["customized"] is True

    resp = client.delete(
        f"/api/v1/platform/tenants/{tenant_id}/permissions/roles/nurse",
        headers=platform_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["roles"]["nurse"]["customized"] is False


def test_platform_endpoints_require_platform_token(seed, client, admin_headers):
    tenant_id = str(seed.tenant.id)
    resp = client.get(f"/api/v1/platform/tenants/{tenant_id}/permissions", headers=admin_headers)
    assert resp.status_code == 401
