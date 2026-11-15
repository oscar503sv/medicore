"""API tests: prescription listing and lifecycle (complete / cancel)."""

from __future__ import annotations

import uuid

from medicore.domain.enums import Role
from tests.presentation.conftest import bearer_login
from tests.support.builders import PASSWORD, build_user


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
            "note": {"subjective": "s", "objective": "o", "assessment": "a", "plan": "p"},
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


REASON = "Patient developed a rash after the first doses"


def _cancel(client, rx_id, headers, reason=REASON):
    return client.post(
        f"/api/v1/prescriptions/{rx_id}/cancel", json={"reason": reason}, headers=headers
    )


def _other_doctor_headers(seed, client):
    doctor = build_user(seed.tenant.id, Role.DOCTOR, email="other@clinica-norte.test")
    seed.factory.store.users[doctor.id.value] = doctor
    return bearer_login(
        client,
        "/api/v1/auth/login",
        {"slug": str(seed.tenant.slug), "email": doctor.email, "password": PASSWORD},
    )


def test_cancel_prescription_returns_the_reason_and_who_closed_it(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]

    resp = _cancel(client, rx_id, auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["cancel_reason"] == REASON
    assert body["closed_by_id"] == str(seed.doctor.id)
    assert body["closed_at"] is not None


def test_cancel_needs_a_body(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]

    resp = client.post(f"/api/v1/prescriptions/{rx_id}/cancel", headers=auth_headers)

    assert resp.status_code == 422
    assert resp.json()["code"] == "request_invalid"


def test_cancel_with_a_short_reason_is_rejected(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]

    resp = _cancel(client, rx_id, auth_headers, reason="short")

    assert resp.status_code == 422
    assert resp.json()["code"] == "prescription.cancel_reason_invalid"
    assert _list(seed, client, auth_headers)[0]["status"] == "active"


def test_another_doctor_cannot_complete_or_cancel(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]
    other = _other_doctor_headers(seed, client)

    complete = client.post(f"/api/v1/prescriptions/{rx_id}/complete", headers=other)
    cancel = _cancel(client, rx_id, other)

    for resp in (complete, cancel):
        assert resp.status_code == 403
        assert resp.json()["code"] == "prescription.not_own"
    assert _list(seed, client, auth_headers)[0]["status"] == "active"


def test_nurse_and_support_cannot_complete_or_cancel(
    seed, client, auth_headers, nurse_headers, support_headers
):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]

    for headers in (nurse_headers, support_headers):
        assert client.post(
            f"/api/v1/prescriptions/{rx_id}/complete", headers=headers
        ).status_code == 403
        assert _cancel(client, rx_id, headers).status_code == 403
    assert _list(seed, client, auth_headers)[0]["status"] == "active"


def test_nurse_sees_the_cancellation_but_not_its_reason(
    seed, client, auth_headers, nurse_headers
):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]
    _cancel(client, rx_id, auth_headers)

    (as_doctor,) = _list(seed, client, auth_headers)
    (as_nurse,) = _list(seed, client, nurse_headers)

    assert as_doctor["cancel_reason"] == REASON
    assert as_nurse["status"] == "cancelled"
    assert as_nurse["closed_at"] is not None
    assert as_nurse["cancel_reason"] is None


def test_cancelled_prescription_is_not_printed(seed, client, auth_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx = _list(seed, client, auth_headers)[0]
    _cancel(client, rx["id"], auth_headers)

    resp = client.get(
        f"/api/v1/print/records/{rx['record_id']}?document=prescription", headers=auth_headers
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "print.nothing_to_print"


def test_receptionist_cannot_complete(seed, client, auth_headers, receptionist_headers):
    _sign_with_prescription(seed, client, auth_headers)
    rx_id = _list(seed, client, auth_headers)[0]["id"]
    resp = client.post(f"/api/v1/prescriptions/{rx_id}/complete", headers=receptionist_headers)
    assert resp.status_code == 403


def test_complete_nonexistent_returns_404(client, auth_headers):
    resp = client.post(f"/api/v1/prescriptions/{uuid.uuid4()}/complete", headers=auth_headers)
    assert resp.status_code == 404
