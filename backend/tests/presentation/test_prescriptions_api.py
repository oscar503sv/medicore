"""API tests: prescription listing and lifecycle (complete / cancel)."""

from __future__ import annotations

import uuid


def _sign_with_prescription(seed, client, headers):
    """Full clinical flow: book → start → fill → add prescription → sign."""
    appt = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(seed.patient.id),
            "doctor_id": str(seed.doctor.id),
            "location_id": str(seed.tenant.primary_location.id),
            "type": "consult",
            "scheduled_start": "2026-06-01T09:00:00",
            "reason": "Control",
        },
        headers=headers,
    ).json()
    cid = client.post(f"/api/v1/consultations/start/{appt['id']}", headers=headers).json()["id"]
    client.patch(
        f"/api/v1/consultations/{cid}/autosave",
        json={
            "vitals": {"heart_rate": 72, "weight": "70"},
            "soap": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
        },
        headers=headers,
    )
    client.post(
        f"/api/v1/consultations/{cid}/diagnoses",
        json={"code": "I10", "label": "Hipertensión"},
        headers=headers,
    )
    client.post(
        f"/api/v1/consultations/{cid}/prescriptions",
        json={"drug": "Enalapril", "dose": "20 mg", "schedule": "1× día", "duration_days": 30},
        headers=headers,
    )
    resp = client.post(
        f"/api/v1/consultations/{cid}/sign",
        json={"chief_complaint": "Control HTA"},
        headers=headers,
    )
    assert resp.status_code == 200


def _list(seed, client, headers):
    resp = client.get(
        f"/api/v1/prescriptions?patient_id={seed.patient.id}", headers=headers
    )
    assert resp.status_code == 200
    return resp.json()["items"]


def test_signing_issues_listable_prescription(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    items = _list(seed, client, auth_headers)
    assert len(items) == 1
    rx = items[0]
    assert rx["drug"] == "Enalapril"
    assert rx["status"] == "active"
    assert rx["prescriber_name"] == seed.doctor.name


def test_complete_then_complete_again_conflicts(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]

    resp = client.post(f"/api/v1/prescriptions/{rx_id}/complete", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # InvalidStateTransition maps to 422 app-wide (same as appointment transitions).
    again = client.post(f"/api/v1/prescriptions/{rx_id}/complete", headers=auth_headers)
    assert again.status_code == 422


def test_cancel_prescription(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]
    resp = client.post(f"/api/v1/prescriptions/{rx_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_receptionist_cannot_complete(seed, client, auth_headers, receptionist_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]
    resp = client.post(f"/api/v1/prescriptions/{rx_id}/complete", headers=receptionist_headers)
    assert resp.status_code == 403


def test_complete_nonexistent_returns_404(client, auth_headers):
    resp = client.post(f"/api/v1/prescriptions/{uuid.uuid4()}/complete", headers=auth_headers)
    assert resp.status_code == 404
