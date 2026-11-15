"""API: the consultation is the doctor's; nursing records vitals; the admin may open it."""

from __future__ import annotations

import pytest

CONSULTATIONS = "/api/v1/consultations"
NOTE_TEXT = "dolor torácico irradiado"
NON_CLINICAL_KEYS = {
    "id", "appointment_id", "patient_id", "doctor_id", "doctor_name", "status", "started_at",
    "vitals", "last_saved_at", "patient", "appointment",
}


def _book(seed, client, headers, start="2026-06-01T09:00:00"):
    return client.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(seed.patient.id), "doctor_id": str(seed.doctor.id),
            "location_id": str(seed.tenant.primary_location.id), "type": "consult",
            "scheduled_start": start, "duration_minutes": 30, "reason": "Control",
        },
        headers=headers,
    ).json()["id"]


@pytest.fixture
def started(seed, client, auth_headers):
    appointment_id = _book(seed, client, auth_headers)
    resp = client.post(f"{CONSULTATIONS}/start/{appointment_id}", headers=auth_headers)
    assert resp.status_code == 201
    consultation_id = resp.json()["id"]
    client.patch(
        f"{CONSULTATIONS}/{consultation_id}/autosave",
        json={"note": {"subjective": NOTE_TEXT}, "vitals": {"heart_rate": 70}},
        headers=auth_headers,
    )
    return appointment_id, consultation_id


def test_start_returns_a_reference_without_the_note(seed, client, auth_headers):
    resp = client.post(
        f"{CONSULTATIONS}/start/{_book(seed, client, auth_headers)}", headers=auth_headers
    )
    assert resp.status_code == 201
    assert set(resp.json()) == {
        "id", "appointment_id", "patient_id", "doctor_id", "status", "started_at"
    }


def test_the_admin_starts_but_never_reads(seed, client, auth_headers, admin_headers):
    appointment_id = _book(seed, client, auth_headers)
    resp = client.post(f"{CONSULTATIONS}/start/{appointment_id}", headers=admin_headers)
    assert resp.status_code == 201 and "note" not in resp.json()
    # A second start finds the existing consultation and still answers with the reference.
    again = client.post(f"{CONSULTATIONS}/start/{appointment_id}", headers=admin_headers)
    assert again.status_code == 201 and "note" not in again.json()
    cid = resp.json()["id"]
    assert client.get(f"{CONSULTATIONS}/{cid}", headers=admin_headers).status_code == 403
    assert client.get(
        f"{CONSULTATIONS}/by-appointment/{appointment_id}/vitals", headers=admin_headers
    ).status_code == 403
    assert client.put(
        f"{CONSULTATIONS}/{cid}/vitals", json={"heart_rate": 70}, headers=admin_headers
    ).status_code == 403


class TestNursing:
    def test_cannot_read_or_edit_the_content(self, client, nurse_headers, started):
        _, cid = started
        assert client.get(f"{CONSULTATIONS}/{cid}", headers=nurse_headers).status_code == 403
        patch = client.patch(
            f"{CONSULTATIONS}/{cid}/autosave", json={"note": {"plan": "x"}}, headers=nurse_headers
        )
        assert patch.status_code == 403
        assert patch.json()["code"] == "permission.missing"

    def test_cannot_start(self, seed, client, auth_headers, nurse_headers):
        appointment_id = _book(seed, client, auth_headers, "2026-06-02T09:00:00")
        assert client.post(
            f"{CONSULTATIONS}/start/{appointment_id}", headers=nurse_headers
        ).status_code == 403

    def test_reads_the_vitals_view_without_clinical_keys(self, client, nurse_headers, started):
        appointment_id, _ = started
        resp = client.get(
            f"{CONSULTATIONS}/by-appointment/{appointment_id}/vitals", headers=nurse_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == NON_CLINICAL_KEYS
        assert NOTE_TEXT not in resp.text
        assert body["vitals"]["heart_rate"] == 70
        assert body["doctor_name"]

    def test_records_vitals_and_the_doctor_sees_them(
        self, client, nurse_headers, auth_headers, started
    ):
        _, cid = started
        resp = client.put(
            f"{CONSULTATIONS}/{cid}/vitals",
            json={"blood_pressure": "120/80", "weight": "68.5"},
            headers=nurse_headers,
        )
        assert resp.status_code == 200
        assert set(resp.json()) == NON_CLINICAL_KEYS
        full = client.get(f"{CONSULTATIONS}/{cid}", headers=auth_headers).json()
        assert full["vitals"]["blood_pressure"] == "120/80"
        assert full["vitals"]["heart_rate"] == 70  # not in the PUT: kept

    def test_an_unknown_appointment_has_no_consultation_yet(
        self, seed, client, auth_headers, nurse_headers
    ):
        appointment_id = _book(seed, client, auth_headers, "2026-06-03T09:00:00")
        resp = client.get(
            f"{CONSULTATIONS}/by-appointment/{appointment_id}/vitals", headers=nurse_headers
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "consultation.not_started"

    def test_cannot_change_a_signed_consultation(
        self, client, nurse_headers, auth_headers, started
    ):
        _, cid = started
        client.patch(
            f"{CONSULTATIONS}/{cid}/autosave",
            json={"note": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"}},
            headers=auth_headers,
        )
        client.post(
            f"{CONSULTATIONS}/{cid}/diagnoses", json={"code": "I10", "label": "HTA"},
            headers=auth_headers,
        )
        assert client.post(
            f"{CONSULTATIONS}/{cid}/sign", json={"chief_complaint": "x"}, headers=auth_headers
        ).status_code == 200
        resp = client.put(
            f"{CONSULTATIONS}/{cid}/vitals", json={"heart_rate": 90}, headers=nurse_headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "consultation.already_signed"


def test_the_receptionist_gets_nothing(client, receptionist_headers, started):
    appointment_id, cid = started
    assert client.get(f"{CONSULTATIONS}/{cid}", headers=receptionist_headers).status_code == 403
    assert client.get(
        f"{CONSULTATIONS}/by-appointment/{appointment_id}/vitals", headers=receptionist_headers
    ).status_code == 403


def test_support_sessions_reach_no_clinical_content(
    seed, client, auth_headers, support_headers, started
):
    appointment_id, cid = started
    for response in (
        client.get(f"{CONSULTATIONS}/{cid}", headers=support_headers),
        client.get(
            f"{CONSULTATIONS}/by-appointment/{appointment_id}/vitals", headers=support_headers
        ),
        client.put(
            f"{CONSULTATIONS}/{cid}/vitals", json={"heart_rate": 1}, headers=support_headers
        ),
        client.post(
            f"{CONSULTATIONS}/start/{_book(seed, client, auth_headers, '2026-06-04T09:00:00')}",
            headers=support_headers,
        ),
    ):
        assert response.status_code == 403
    assert client.patch(
        f"{CONSULTATIONS}/{cid}/autosave", json={"note": {"plan": "x"}}, headers=support_headers
    ).status_code == 403


def test_support_denial_on_start_names_the_guard(seed, client, auth_headers, support_headers):
    appointment_id = _book(seed, client, auth_headers)
    resp = client.post(f"{CONSULTATIONS}/start/{appointment_id}", headers=support_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "support.clinical_forbidden"


def test_a_partial_autosave_keeps_the_other_vitals(client, auth_headers, started):
    _, cid = started
    resp = client.patch(
        f"{CONSULTATIONS}/{cid}/autosave", json={"vitals": {"weight": "70"}}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["vitals"]["heart_rate"] == 70
    assert resp.json()["vitals"]["weight"] == "70"


def test_an_explicit_null_clears_a_vital(client, auth_headers, started):
    _, cid = started
    resp = client.patch(
        f"{CONSULTATIONS}/{cid}/autosave", json={"vitals": {"heart_rate": None}},
        headers=auth_headers,
    )
    assert resp.json()["vitals"]["heart_rate"] is None


def test_the_audit_trail_names_keys_and_never_the_text(
    client, admin_headers, auth_headers, started
):
    _, cid = started
    client.get(f"{CONSULTATIONS}/{cid}", headers=auth_headers)
    trail = client.get("/api/v1/audit", params={"category": "consultation"}, headers=admin_headers)
    assert trail.status_code == 200
    actions = {item["action"] for item in trail.json()["items"]}
    expected = {"consultation.note_updated", "consultation.vitals_updated", "consultation.viewed"}
    assert expected <= actions
    assert NOTE_TEXT not in trail.text
