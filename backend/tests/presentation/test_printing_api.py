"""API tests: printable documents, medical certificates, exam orders and print settings."""

from __future__ import annotations

from datetime import date, datetime

from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.prescription import PrescriptionSnapshot
from medicore.domain.enums import ClinicalRecordType
from medicore.domain.shared.identifiers import RecordId
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals


def _record(seed):
    record = MedicalRecord(
        id=RecordId.new(), tenant_id=seed.tenant.id, code="REC-1", patient_id=seed.patient.id,
        author_id=seed.doctor.id, type=ClinicalRecordType.CONSULTATION,
        encounter_at=datetime(2026, 5, 20, 9), location_name="Sede", chief_complaint="Fiebre",
        soap=SoapNote(plan="Líquidos"), vitals=Vitals(), signed_at=datetime(2026, 5, 20, 9, 30),
        signed_by_id=seed.doctor.id,
        prescriptions=(PrescriptionSnapshot("Paracetamol", "500 mg", "c/8 h",
                                            date(2026, 5, 20)),),
    )
    seed.factory.store.medical_records[record.id.value] = record
    return record


def test_prescription_print(client, seed, auth_headers):
    record = _record(seed)
    resp = client.get(f"/api/v1/print/records/{record.id}?document=prescription",
                      headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["indications"] == "Líquidos"
    assert body["context"]["clinic"]["paper"] == "half_letter"
    assert body["record"]["prescriptions"][0]["drug"] == "Paracetamol"
    resp = client.get(f"/api/v1/print/records/{record.id}?document=exams", headers=auth_headers)
    assert resp.status_code == 400 and resp.json()["code"] == "print.nothing_to_print"
    resp = client.get(f"/api/v1/print/records/{record.id}?document=bill", headers=auth_headers)
    assert resp.status_code == 422


def test_certificate_issue_list_print_void(client, seed, auth_headers):
    record = _record(seed)
    resp = client.post(f"/api/v1/records/{record.id}/certificates", headers=auth_headers,
                       json={"kind": "rest", "rest_from": "2026-05-20", "rest_days": 2})
    assert resp.status_code == 201, resp.text
    cert = resp.json()
    assert (cert["rest_until"], cert["diagnosis"]) == ("2026-05-21", None)
    listed = client.get(f"/api/v1/patients/{seed.patient.id}/certificates",
                        headers=auth_headers).json()
    assert [c["id"] for c in listed] == [cert["id"]]
    resp = client.get(f"/api/v1/print/certificates/{cert['id']}", headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["certificate"]["code"] == cert["code"]
    resp = client.post(f"/api/v1/certificates/{cert['id']}/void", headers=auth_headers,
                       json={"reason": "Fecha equivocada"})
    assert resp.status_code == 200 and resp.json()["voided_at"]
    resp = client.get(f"/api/v1/print/certificates/{cert['id']}", headers=auth_headers)
    assert resp.json()["code"] == "print.certificate_voided"


def test_print_settings_and_location_phone(client, seed, admin_headers, auth_headers):
    resp = client.put("/api/v1/organization/print-settings", headers=admin_headers,
                      json={"paper": "letter", "letterhead": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["print_settings"] == {"paper": "letter", "letterhead": True}
    loc = seed.tenant.primary_location.id
    resp = client.patch(f"/api/v1/organization/locations/{loc}", headers=admin_headers,
                        json={"phone": "2222-3333"})
    assert resp.json()["locations"][0]["phone"] == "2222-3333"
    resp = client.put("/api/v1/organization/print-settings", headers=auth_headers,
                      json={"paper": "letter", "letterhead": False})
    assert resp.status_code == 403


def test_jvpm_on_profile(client, auth_headers):
    resp = client.patch("/api/v1/auth/me", headers=auth_headers, json={"jvpm": "12345"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["jvpm"] == "12345"
    resp = client.patch("/api/v1/auth/me", headers=auth_headers, json={"jvpm": "12-3"})
    assert resp.status_code == 422 and resp.json()["code"] == "user.invalid_jvpm"


def test_agenda_and_vaccination_card(client, seed, auth_headers):
    resp = client.get("/api/v1/print/agenda?date=2026-06-01", headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["rows"] == []
    resp = client.get(f"/api/v1/print/vaccination-card/{seed.patient.id}", headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["patient"]["code"] == seed.patient.code
