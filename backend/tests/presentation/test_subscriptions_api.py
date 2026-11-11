"""API tests: plan catalog and clinic subscriptions (platform console + clinic view)."""

from __future__ import annotations


def _url(seed, suffix: str = "") -> str:
    return f"/api/v1/platform/tenants/{seed.tenant.id}/subscription{suffix}"


def test_catalog_lists_plans_with_prices_as_strings(client, platform_headers):
    resp = client.get("/api/v1/platform/plans", headers=platform_headers)
    assert resp.status_code == 200
    body = resp.json()
    clinica = next(p for p in body["plans"] if p["code"] == "clinica")
    assert clinica["monthly_price"] == "79.00"
    assert clinica["limits"] == {
        "doctors": 3, "support_users": 3, "locations": 1, "storage_gb": 3,
    }
    assert body["addons"]["bundle_price"] == "29.00"


def test_catalog_requires_platform_admin(client, admin_headers):
    assert client.get("/api/v1/platform/plans", headers=admin_headers).status_code == 401


def test_update_plan(client, platform_headers):
    resp = client.put(
        "/api/v1/platform/plans/clinica",
        headers=platform_headers,
        json={
            "name": "Clínica",
            "monthly_price": "85",
            "limits": {"doctors": 4, "support_users": 3, "locations": 1, "storage_gb": 3},
            "features": ["user_permissions"],
            "active": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["monthly_price"], resp.json()["limits"]["doctors"]) == ("85.00", 4)


def test_update_plan_rejects_negative_limit(client, platform_headers):
    resp = client.put(
        "/api/v1/platform/plans/clinica",
        headers=platform_headers,
        json={"name": "Clínica", "monthly_price": "79", "limits": {"doctors": -1}},
    )
    assert resp.status_code == 422


def test_update_addon_pricing(client, platform_headers):
    resp = client.put(
        "/api/v1/platform/addon-pricing",
        headers=platform_headers,
        json={
            "prices": {"vaccination": "12", "applications": "15", "procedures": "15"},
            "bundle_price": "30",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["prices"]["vaccination"] == "12.00"


def test_get_and_update_tenant_subscription(seed, client, platform_headers):
    resp = client.get(_url(seed), headers=platform_headers)
    assert resp.status_code == 200
    assert resp.json()["plan"]["code"] == "clinica_plus"

    resp = client.put(
        _url(seed),
        headers=platform_headers,
        json={
            "plan_code": "clinica",
            "modules": ["vaccination"],
            "period_end": "2099-01-31",
            "grace_days": 5,
            "limit_overrides": {"doctors": 5},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plan"]["code"] == "clinica"
    assert body["modules"] == ["vaccination"]
    assert body["status"] == "active"
    assert body["limits"]["doctors"] == 5
    assert body["monthly_price"] == "89.00"

    tenant = client.get(f"/api/v1/platform/tenants/{seed.tenant.id}", headers=platform_headers)
    assert tenant.json()["subscription"]["plan_code"] == "clinica"


def test_empty_overrides_are_stored_as_none(seed, client, platform_headers):
    resp = client.put(
        _url(seed),
        headers=platform_headers,
        json={"plan_code": "clinica", "period_end": "2099-01-31", "limit_overrides": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["limit_overrides"] is None


def test_unknown_plan_is_rejected_with_code(seed, client, platform_headers):
    resp = client.put(
        _url(seed), headers=platform_headers, json={"plan_code": "gold", "period_end": None}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "plan.unavailable"


def test_start_trial(seed, client, platform_headers):
    resp = client.post(_url(seed, "/trial"), headers=platform_headers, json={"days": 7})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["status"], resp.json()["is_trial"]) == ("trial", True)


def test_create_tenant_requires_trial_or_period(client, platform_headers):
    resp = client.post(
        "/api/v1/platform/tenants",
        headers=platform_headers,
        json={
            "legal_name": "Clínica Oeste SL", "tax_id": "B78", "slug": "clinica-oeste",
            "location_name": "Santa Ana", "admin_name": "Admin Oeste",
            "admin_email": "admin@oeste.test", "admin_password": "temp-pass-123",
            "plan_code": "clinica",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "plan.period_required"


def test_clinic_admin_reads_own_plan(client, admin_headers):
    resp = client.get("/api/v1/organization/subscription", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["plan"]["code"] == "clinica_plus"


def test_doctor_cannot_read_clinic_plan(client, auth_headers):
    resp = client.get("/api/v1/organization/subscription", headers=auth_headers)
    assert resp.status_code == 403
