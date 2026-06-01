"""API tests: appointments and slot resolution."""

from __future__ import annotations

MONDAY = "2026-06-01"  # Monday within Mon-Fri 09:00-13:00 availability


def _booking_payload(seed, start="2026-06-01T09:00:00"):
    return {
        "patient_id": str(seed.patient.id),
        "doctor_id": str(seed.doctor.id),
        "location_id": str(seed.tenant.primary_location.id),
        "type": "consult",
        "scheduled_start": start,
        "duration_minutes": 30,
        "reason": "Control tensión",
    }


def test_get_slots_within_availability(seed, client, auth_headers):
    resp = client.get(
        f"/api/v1/appointments/slots?doctor_id={seed.doctor.id}&on={MONDAY}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    slots = resp.json()
    assert len(slots) == 8  # 240 min / 30
    assert slots[0]["status"] == "free"


def test_create_appointment(seed, client, auth_headers):
    resp = client.post(
        "/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "scheduled"
    assert data["code"].startswith("A-")


def test_slot_shows_taken_after_booking(seed, client, auth_headers):
    client.post("/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers)
    slots = client.get(
        f"/api/v1/appointments/slots?doctor_id={seed.doctor.id}&on={MONDAY}",
        headers=auth_headers,
    ).json()
    assert slots[0]["status"] == "taken"
    assert slots[1]["status"] == "free"


def test_booking_outside_hours_rejected(seed, client, auth_headers):
    resp = client.post(
        "/api/v1/appointments",
        json=_booking_payload(seed, start="2026-06-01T15:00:00"),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_overlapping_booking_rejected(seed, client, auth_headers):
    client.post("/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers)
    resp = client.post(
        "/api/v1/appointments",
        json=_booking_payload(seed, start="2026-06-01T09:15:00"),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_confirm_and_cancel_appointment(seed, client, auth_headers):
    appt = client.post(
        "/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers
    ).json()
    appt_id = appt["id"]

    confirmed = client.post(
        f"/api/v1/appointments/{appt_id}/confirm", headers=auth_headers
    ).json()
    assert confirmed["status"] == "confirmed"

    cancelled = client.post(
        f"/api/v1/appointments/{appt_id}/cancel", headers=auth_headers
    ).json()
    assert cancelled["status"] == "cancelled"


def test_weekly_schedule(seed, client, auth_headers):
    resp = client.get(
        f"/api/v1/appointments/schedule?week_start=2026-06-01&doctor_id={seed.doctor.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    schedule = resp.json()["schedule"]
    assert len(schedule) == 7
