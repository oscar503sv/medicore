"""API: nursing records vitals from the confirmed appointment, before the consultation."""

from __future__ import annotations

import pytest

APPOINTMENTS = "/api/v1/appointments"
CONSULTATIONS = "/api/v1/consultations"
RESPONSE_KEYS = {
    "appointment_id", "consultation_id", "phase", "consultation_status", "doctor_name",
    "vitals", "last_saved_at", "patient", "appointment",
}


def _book(seed, client, headers, start="2026-06-01T09:00:00"):
    return client.post(
        APPOINTMENTS,
        json={
            "patient_id": str(seed.patient.id), "doctor_id": str(seed.doctor.id),
            "location_id": str(seed.tenant.primary_location.id), "type": "consult",
            "scheduled_start": start, "duration_minutes": 30, "reason": "Control",
        },
        headers=headers,
    ).json()["id"]


@pytest.fixture
def confirmed(seed, client, auth_headers):
    appointment_id = _book(seed, client, auth_headers)
    assert client.post(
        f"{APPOINTMENTS}/{appointment_id}/confirm", headers=auth_headers
    ).status_code == 200
    return appointment_id


def _put(client, headers, appointment_id, **vitals):
    return client.put(f"{APPOINTMENTS}/{appointment_id}/vitals", json=vitals, headers=headers)


def test_nursing_records_and_reads_the_waiting_room_vitals(client, nurse_headers, confirmed):
    resp = _put(client, nurse_headers, confirmed, blood_pressure="120/80", heart_rate=70)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == RESPONSE_KEYS
    assert (body["phase"], body["consultation_id"], body["consultation_status"]) == (
        "triage", None, None,
    )
    assert body["vitals"]["blood_pressure"] == "120/80"
    assert body["last_saved_at"] is not None
    assert body["patient"] is not None and body["appointment"]["id"] == confirmed

    again = client.get(f"{APPOINTMENTS}/{confirmed}/vitals", headers=nurse_headers)
    assert again.status_code == 200 and again.json()["vitals"]["heart_rate"] == 70


def test_the_appointment_never_exposes_the_pre_vitals(
    client, nurse_headers, auth_headers, confirmed
):
    _put(client, nurse_headers, confirmed, heart_rate=70)

    for response in (
        client.get("/api/v1/appointments?on=2026-06-01", headers=auth_headers),
        client.get(f"{APPOINTMENTS}/upcoming", headers=auth_headers),
    ):
        assert response.status_code == 200
        assert "pre_vitals" not in response.text
        assert "pre_vitals_saved_at" not in response.text
    body = client.get(f"{APPOINTMENTS}/{confirmed}/vitals", headers=nurse_headers).json()
    assert "pre_vitals" not in body["appointment"]


def test_the_doctor_finds_the_vitals_in_the_consultation_once_started(
    client, nurse_headers, auth_headers, confirmed
):
    _put(client, nurse_headers, confirmed, heart_rate=70)

    started = client.post(f"{CONSULTATIONS}/start/{confirmed}", headers=auth_headers)
    assert started.status_code == 201
    full = client.get(f"{CONSULTATIONS}/{started.json()['id']}", headers=auth_headers).json()
    assert full["vitals"]["heart_rate"] == 70

    body = client.get(f"{APPOINTMENTS}/{confirmed}/vitals", headers=nurse_headers).json()
    assert (body["phase"], body["consultation_id"]) == ("consultation", started.json()["id"])
    # The legacy pair keeps working on the same data.
    legacy = client.get(
        f"{CONSULTATIONS}/by-appointment/{confirmed}/vitals", headers=nurse_headers
    )
    assert legacy.status_code == 200 and legacy.json()["vitals"]["heart_rate"] == 70
    assert _put(client, nurse_headers, confirmed, spo2=98).json()["phase"] == "consultation"


def test_a_scheduled_appointment_does_not_take_vitals_yet(
    seed, client, nurse_headers, auth_headers
):
    scheduled = _book(seed, client, auth_headers, "2026-06-02T09:00:00")
    for resp in (
        _put(client, nurse_headers, scheduled, heart_rate=70),
        client.get(f"{APPOINTMENTS}/{scheduled}/vitals", headers=nurse_headers),
    ):
        assert resp.status_code == 422
        assert resp.json()["code"] == "appointment.vitals_closed"


def test_an_invalid_reading_is_refused(client, nurse_headers, confirmed):
    resp = _put(client, nurse_headers, confirmed, blood_pressure="high")
    assert resp.status_code == 422
    assert resp.json()["code"] == "vitals.invalid_blood_pressure"


def test_an_unknown_appointment_is_not_found(client, nurse_headers):
    resp = client.get(
        f"{APPOINTMENTS}/00000000-0000-4000-8000-000000000000/vitals", headers=nurse_headers
    )
    assert resp.status_code == 404


def test_receptionist_admin_and_support_are_refused(
    client, receptionist_headers, admin_headers, support_headers, confirmed
):
    for headers in (receptionist_headers, admin_headers, support_headers):
        assert client.get(
            f"{APPOINTMENTS}/{confirmed}/vitals", headers=headers
        ).status_code == 403
        assert _put(client, headers, confirmed, heart_rate=1).status_code == 403


def test_the_owner_doctor_may_record_them_too(client, auth_headers, confirmed):
    assert _put(client, auth_headers, confirmed, heart_rate=70).status_code == 200
