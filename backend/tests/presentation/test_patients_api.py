"""API tests: patients endpoints."""

from __future__ import annotations


def test_list_patients(seed, client, auth_headers):
    resp = client.get("/api/v1/patients", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(p["id"] == str(seed.patient.id) for p in data["items"])
    # Every item exposes the next-visit field (None when the patient has no upcoming appointment).
    assert all("next_visit" in p for p in data["items"])


def test_list_patients_search(seed, client, auth_headers):
    # search by code prefix, no accents involved
    resp = client.get("/api/v1/patients?q=P-00", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_create_patient(client, auth_headers):
    resp = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Carlos",
            "last_name": "Martínez",
            "sex": "male",
            "date_of_birth": "1990-03-15",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["first_name"] == "Carlos"
    assert data["code"].startswith("P-")


def test_get_patient_detail(seed, client, auth_headers):
    resp = client.get(f"/api/v1/patients/{seed.patient.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["patient"]["id"] == str(seed.patient.id)
    assert "records_count" in data


def test_get_nonexistent_patient_returns_404(client, auth_headers):
    import uuid
    resp = client.get(f"/api/v1/patients/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


def test_receptionist_cannot_list_records(seed, client, receptionist_headers):
    resp = client.get("/api/v1/records", headers=receptionist_headers)
    assert resp.status_code == 403
