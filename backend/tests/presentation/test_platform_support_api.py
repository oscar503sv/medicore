"""API tests: support reasons and the clinic-side trail of console actions."""

from __future__ import annotations

import pytest

TENANT_URL = "/api/v1/platform/tenants"


@pytest.mark.parametrize("body", [{}, {"reason": "   "}, {"reason": "x" * 501}])
def test_impersonation_needs_a_valid_reason(seed, client, platform_headers, body):
    resp = client.post(
        f"{TENANT_URL}/{seed.tenant.id}/impersonate", json=body, headers=platform_headers
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "request_invalid"
    assert resp.json()["params"]["fields"] == "reason"


def test_reset_needs_a_reason(seed, client, platform_headers):
    resp = client.post(
        f"{TENANT_URL}/{seed.tenant.id}/users/{seed.doctor.id}/reset-password",
        json={"password": "Volcan-Izalco-77"},
        headers=platform_headers,
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["params"]["fields"] == "reason"


def test_a_reset_reaches_the_clinic_audit_and_inbox(seed, client, platform_headers, admin_headers):
    resp = client.post(
        f"{TENANT_URL}/{seed.tenant.id}/users/{seed.doctor.id}/reset-password",
        json={"password": "Volcan-Izalco-77", "reason": "Forgot the password"},
        headers=platform_headers,
    )
    assert resp.status_code == 200, resp.text

    audit = client.get("/api/v1/audit?category=user", headers=admin_headers)
    [entry] = [e for e in audit.json()["items"] if e["action"] == "user.password_reset"]
    assert entry["metadata"]["via"] == "platform_support"
    assert entry["metadata"]["reason"] == "Forgot the password"
    assert entry["actor_name"] is None
    assert entry["actor_id"] == str(seed.platform_admin.id)

    inbox = client.get("/api/v1/notifications?category=support", headers=admin_headers)
    assert [n["type"] for n in inbox.json()["items"]] == ["support.password_reset"]
