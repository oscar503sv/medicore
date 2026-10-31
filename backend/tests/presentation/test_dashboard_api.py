"""API tests for the dashboard summary."""

from __future__ import annotations


def test_requires_authentication(client):
    assert client.get("/api/v1/dashboard/summary").status_code == 401


def test_summary_shape(client, admin_headers):
    resp = client.get("/api/v1/dashboard/summary", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {
        "day",
        "appointments_today",
        "appointments_delta_pct",
        "pending_today",
        "patients_total",
        "patients_delta_pct",
        "occupancy_pct",
        "occupancy_delta_pts",
    }
    assert body["patients_total"] == 1
    assert body["appointments_today"] == 0
