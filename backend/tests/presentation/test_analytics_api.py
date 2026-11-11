"""API tests: practice metrics and the clinic's practice model."""

from __future__ import annotations


def test_doctor_gets_own_metrics_and_staff_is_refused(client, auth_headers,
                                                      receptionist_headers):
    resp = client.get("/api/v1/analytics/overview", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["scope"], body["money"], body["tier"]) == ("own", True, "operations")
    assert body["current"]["income"] == "0.00"
    assert len(body["trend"]) == 12

    resp = client.get("/api/v1/analytics/overview", headers=receptionist_headers)
    assert resp.status_code == 403 and resp.json()["code"] == "analytics.not_allowed"


def test_invalid_range(client, admin_headers):
    resp = client.get("/api/v1/analytics/overview?period=range&start=2026-05-10&end=2026-05-01",
                      headers=admin_headers)
    assert resp.status_code == 400 and resp.json()["code"] == "analytics.invalid_range"
    resp = client.get("/api/v1/analytics/overview?period=year", headers=admin_headers)
    assert resp.status_code == 422


def test_admin_sees_clinic_without_money(client, admin_headers):
    body = client.get("/api/v1/analytics/overview", headers=admin_headers).json()
    assert (body["scope"], body["money"], body["current"]["income"]) == ("clinic", False, None)
    assert body["doctors"] == []


def test_practice_model(client, admin_headers, auth_headers):
    assert client.get("/api/v1/permissions", headers=admin_headers).json()[
        "practice_model"] == "associated"
    resp = client.put("/api/v1/permissions/practice-model", json={"model": "employed"},
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["practice_model"] == "employed"
    assert "analytics.money" in body["roles"]["admin"]["effective"]
    assert "fees.manage_own" not in body["roles"]["doctor"]["effective"]

    resp = client.put("/api/v1/permissions/practice-model", json={"model": "employed"},
                      headers=auth_headers)
    assert resp.status_code == 403
