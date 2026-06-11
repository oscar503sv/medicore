"""API tests: consultation lifecycle (start → edit → sign)."""

from __future__ import annotations


def _book_and_start(seed, client, headers):
    """Helper: create appointment + start consultation, return both IDs."""
    appt = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(seed.patient.id),
            "doctor_id": str(seed.doctor.id),
            "location_id": str(seed.tenant.primary_location.id),
            "type": "consult",
            "scheduled_start": "2026-06-01T09:00:00",
            "duration_minutes": 30,
            "reason": "Test",
        },
        headers=headers,
    ).json()

    c = client.post(
        f"/api/v1/consultations/start/{appt['id']}", headers=headers
    ).json()
    return appt["id"], c["id"]


def test_start_consultation(seed, client, auth_headers):
    appt = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(seed.patient.id),
            "doctor_id": str(seed.doctor.id),
            "location_id": str(seed.tenant.primary_location.id),
            "type": "consult",
            "scheduled_start": "2026-06-01T09:00:00",
            "duration_minutes": 30,
            "reason": "Control",
        },
        headers=auth_headers,
    ).json()

    resp = client.post(f"/api/v1/consultations/start/{appt['id']}", headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "draft"


def test_get_consultation(seed, client, auth_headers):
    _, cid = _book_and_start(seed, client, auth_headers)
    resp = client.get(f"/api/v1/consultations/{cid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == cid


def test_autosave_vitals_and_soap(seed, client, auth_headers):
    _, cid = _book_and_start(seed, client, auth_headers)
    resp = client.patch(
        f"/api/v1/consultations/{cid}/autosave",
        json={
            "vitals": {"heart_rate": 72, "blood_pressure": "120/80"},
            "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["vitals"]["heart_rate"] == 72
    assert data["completion_percent"] == 80  # soap=60% + vitals(heart_rate)=20%, no dx


def test_sign_complete_consultation(seed, client, auth_headers):
    _, cid = _book_and_start(seed, client, auth_headers)
    # Fill enough for signing
    client.patch(
        f"/api/v1/consultations/{cid}/autosave",
        json={
            "vitals": {"heart_rate": 72, "weight": "70"},
            "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
        },
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/consultations/{cid}/diagnoses",
        json={"code": "I10", "label": "Hipertensión"},
        headers=auth_headers,
    )
    resp = client.post(
        f"/api/v1/consultations/{cid}/sign",
        json={"chief_complaint": "Control HTA"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    record = resp.json()
    assert record["status"] == "signed"
    assert record["code"].startswith("REC-")


def test_records_list_includes_patient_name_and_chosen_type(seed, client, auth_headers):
    _, cid = _book_and_start(seed, client, auth_headers)
    client.patch(
        f"/api/v1/consultations/{cid}/autosave",
        json={
            "vitals": {"heart_rate": 72, "weight": "70"},
            "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
        },
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/consultations/{cid}/diagnoses",
        json={"code": "I10", "label": "Hipertensión"},
        headers=auth_headers,
    )
    client.post(
        f"/api/v1/consultations/{cid}/sign",
        json={"chief_complaint": "Análisis"},
        headers=auth_headers,
    )

    resp = client.get("/api/v1/records", headers=auth_headers)
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) >= 1
    rec = next(r for r in records if r["chief_complaint"] == "Análisis")
    assert rec["type"] == "consultation"  # signing a consultation always yields CONSULTATION
    assert rec["patient_name"] == seed.patient.full_name


def test_sign_incomplete_returns_422(seed, client, auth_headers):
    _, cid = _book_and_start(seed, client, auth_headers)
    resp = client.post(
        f"/api/v1/consultations/{cid}/sign",
        json={"chief_complaint": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_nurse_cannot_sign(seed, client):
    """Nurse can start (clinical) but cannot sign."""
    from tests.presentation.conftest import bearer_login
    from tests.support.builders import PASSWORD

    nurse_headers = bearer_login(
        client,
        "/api/v1/auth/login",
        {"slug": str(seed.tenant.slug), "email": seed.nurse.email, "password": PASSWORD},
    )

    # book via doctor
    doc_headers = bearer_login(
        client,
        "/api/v1/auth/login",
        {"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )

    _, cid = _book_and_start(seed, client, doc_headers)

    resp = client.post(
        f"/api/v1/consultations/{cid}/sign",
        json={"chief_complaint": "x"},
        headers=nurse_headers,
    )
    assert resp.status_code == 403
