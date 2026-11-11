"""API tests: timezone stays with support, the console opens sites."""

from __future__ import annotations


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
