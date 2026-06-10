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
        "reason": "Control tensión",
    }


def test_get_slots_within_availability(seed, client, auth_headers):
    resp = client.get(
        f"/api/v1/appointments/slots?doctor_id={seed.doctor.id}&on={MONDAY}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    slots = resp.json()
    free = [s for s in slots if s["status"] == "free"]
    assert len(free) == 8  # 240 min / 30 within the 09:00–13:00 block
    assert free[0]["start"].endswith("09:00:00")
    # Slot duration comes from the doctor's rules (30 min).
    assert free[0]["end"].endswith("09:30:00")


def test_invalid_uuid_returns_422(seed, client, auth_headers):
    resp = client.get(
        f"/api/v1/appointments/slots?doctor_id=not-a-uuid&on={MONDAY}",
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_appointment(seed, client, auth_headers):
    resp = client.post(
        "/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "scheduled"
    assert data["code"].startswith("A-")
    # Duration comes from the doctor's rules, not from the request.
    assert data["duration_minutes"] == 30


def test_create_ignores_client_duration(seed, client, auth_headers):
    payload = {**_booking_payload(seed), "duration_minutes": 60}  # legacy field — ignored
    resp = client.post("/api/v1/appointments", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["duration_minutes"] == 30


def test_reschedule_uses_doctor_duration(seed, client, auth_headers):
    appt = client.post(
        "/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers
    ).json()
    resp = client.put(
        f"/api/v1/appointments/{appt['id']}/reschedule",
        json={"new_start": "2026-06-01T10:00:00", "new_duration": 90},  # legacy — ignored
        headers=auth_headers,
    )
    assert resp.status_code == 200
    moved = resp.json()
    assert moved["scheduled_start"].endswith("10:00:00")
    assert moved["duration_minutes"] == 30


def test_booking_options_include_slot_minutes(seed, client, auth_headers):
    resp = client.get("/api/v1/appointments/booking-options", headers=auth_headers)
    assert resp.status_code == 200
    doctor = next(
        d for d in resp.json()["doctors"] if d["id"] == str(seed.doctor.id)
    )
    assert doctor["slot_minutes"] == 30


def test_slot_shows_taken_after_booking(seed, client, auth_headers):
    client.post("/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers)
    slots = client.get(
        f"/api/v1/appointments/slots?doctor_id={seed.doctor.id}&on={MONDAY}",
        headers=auth_headers,
    ).json()
    nine = next(s for s in slots if s["start"].endswith("09:00:00"))
    nine_thirty = next(s for s in slots if s["start"].endswith("09:30:00"))
    assert nine["status"] == "taken"
    assert nine_thirty["status"] == "free"


def test_booking_outside_hours_rejected(seed, client, auth_headers):
    resp = client.post(
        "/api/v1/appointments",
        json=_booking_payload(seed, start="2026-06-01T15:00:00"),
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_overlapping_booking_rejected(seed, client, auth_headers):
    client.post("/api/v1/appointments", json=_booking_payload(seed), headers=auth_headers)
    resp = client.post(
        "/api/v1/appointments",
        json=_booking_payload(seed, start="2026-06-01T09:15:00"),
        headers=auth_headers,
    )
    assert resp.status_code == 409


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
