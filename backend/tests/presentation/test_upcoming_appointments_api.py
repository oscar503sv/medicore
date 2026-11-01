"""API tests for GET /appointments/upcoming (dashboard's next appointments)."""

from __future__ import annotations

BASE = "/api/v1/appointments"


def _book(client, seed, headers, start: str) -> dict:
    resp = client.post(
        BASE,
        json={
            "patient_id": str(seed.patient.id),
            "doctor_id": str(seed.doctor.id),
            "location_id": str(seed.tenant.primary_location.id),
            "type": "consult",
            "scheduled_start": start,
            "reason": "Control",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_returns_next_appointments_with_names(client, seed, auth_headers, receptionist_headers):
    later = _book(client, seed, receptionist_headers, "2026-06-02T10:00:00")
    first = _book(client, seed, receptionist_headers, "2026-06-01T09:00:00")

    body = client.get(f"{BASE}/upcoming?limit=5", headers=auth_headers).json()

    assert [a["id"] for a in body] == [first["id"], later["id"]]
    assert body[0]["patient_name"] == seed.patient.full_name


def test_limit_is_validated(client, auth_headers):
    resp = client.get(f"{BASE}/upcoming?limit=0", headers=auth_headers)
    assert resp.status_code == 422
