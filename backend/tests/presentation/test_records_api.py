"""API tests: who reaches the records list, a record's content, the history and the vitals."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from medicore.domain.enums import Role
from medicore.domain.value_objects.vitals import Vitals
from tests.support.builders import PASSWORD, build_user
from tests.support.records import store_record

RECORDS = "/api/v1/records"


@pytest.fixture
def record(seed):
    return store_record(
        seed,
        code="REC-2026-0001",
        encounter_at=datetime(2026, 5, 20, 9),
        chief_complaint="dolor secreto",
        vitals=Vitals(heart_rate=72, weight=Decimal("70")),
    )


@pytest.fixture
def other_doctor_headers(seed, client):
    other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@clinica.test")
    seed.factory.store.users[other.id.value] = other
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": other.email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    token = client.cookies.get("mc_session")
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def _statuses(client, seed, record, headers) -> tuple[int, int, int, int]:
    pid = seed.patient.id
    return (
        client.get(RECORDS, headers=headers).status_code,
        client.get(f"{RECORDS}/{record.id}", headers=headers).status_code,
        client.get(f"/api/v1/patients/{pid}/records", headers=headers).status_code,
        client.get(f"/api/v1/patients/{pid}/vitals", headers=headers).status_code,
    )


class TestListShape:
    def test_a_page_of_summaries_without_clinical_content(
        self, seed, client, auth_headers, record
    ):
        resp = client.get(RECORDS, headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert (body["total"], body["offset"], body["limit"]) == (1, 0, 25)
        [item] = body["items"]
        assert item["code"] == "REC-2026-0001"
        assert item["signed_by_name"] == seed.doctor.name
        for hidden in ("note", "vitals", "diagnoses", "prescriptions", "chief_complaint"):
            assert hidden not in item
        assert "dolor secreto" not in resp.text

    @pytest.mark.parametrize("query", ["limit=101", "limit=0", "offset=-1", "q=" + "x" * 101])
    def test_out_of_bounds_parameters_are_422(self, client, auth_headers, query):
        assert client.get(f"{RECORDS}?{query}", headers=auth_headers).status_code == 422

    def test_filters_reach_the_server(self, client, auth_headers, record):
        assert client.get(f"{RECORDS}?q=0001", headers=auth_headers).json()["total"] == 1
        assert client.get(f"{RECORDS}?q=zzz", headers=auth_headers).json()["total"] == 0
        assert client.get(f"{RECORDS}?type=procedure", headers=auth_headers).json()["total"] == 0
        assert client.get(f"{RECORDS}?type=nonsense", headers=auth_headers).status_code == 422
        resp = client.get(f"{RECORDS}?date_from=2026-05-21", headers=auth_headers)
        assert resp.json()["total"] == 0
        resp = client.get(
            f"{RECORDS}?date_from=2026-05-21&date_to=2026-05-01", headers=auth_headers
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "records.invalid_range"


class TestAccessByRole:
    def test_doctor_reads_everything(self, seed, client, auth_headers, record):
        assert _statuses(client, seed, record, auth_headers) == (200, 200, 200, 200)

    def test_another_doctor_reads_everything(
        self, seed, client, other_doctor_headers, record
    ):
        assert _statuses(client, seed, record, other_doctor_headers) == (200, 200, 200, 200)

    def test_admin_and_nurse_get_the_list_and_vitals_only(
        self, seed, client, admin_headers, nurse_headers, record
    ):
        assert _statuses(client, seed, record, admin_headers) == (200, 403, 403, 200)
        assert _statuses(client, seed, record, nurse_headers) == (200, 403, 403, 200)

    def test_receptionist_gets_nothing(self, seed, client, receptionist_headers, record):
        assert _statuses(client, seed, record, receptionist_headers) == (403, 403, 403, 403)

    def test_support_sessions_are_like_an_admin(self, seed, client, support_headers, record):
        assert _statuses(client, seed, record, support_headers) == (200, 403, 403, 200)

    def test_the_denial_names_the_missing_permission(
        self, client, nurse_headers, record
    ):
        resp = client.get(f"{RECORDS}/{record.id}", headers=nurse_headers)
        assert resp.json()["code"] == "permission.missing"
        assert resp.json()["params"]["permission"] == "records.read_clinical"


class TestPatientViews:
    def test_vitals_are_just_the_readings(self, seed, client, nurse_headers, record):
        resp = client.get(f"/api/v1/patients/{seed.patient.id}/vitals", headers=nurse_headers)
        [reading] = resp.json()
        assert reading["record_code"] == "REC-2026-0001"
        assert reading["vitals"]["heart_rate"] == 72
        assert "note" not in reading

    def test_patient_detail_embeds_vitals_and_recent_records_for_nursing(
        self, seed, client, nurse_headers, record
    ):
        data = client.get(f"/api/v1/patients/{seed.patient.id}", headers=nurse_headers).json()
        assert data["latest_vitals"]["record_code"] == "REC-2026-0001"
        assert [r["code"] for r in data["recent_records"]] == ["REC-2026-0001"]
        assert "dolor secreto" not in str(data)

    def test_patient_detail_is_empty_for_reception(
        self, seed, client, receptionist_headers, record
    ):
        data = client.get(
            f"/api/v1/patients/{seed.patient.id}", headers=receptionist_headers
        ).json()
        assert data["latest_vitals"] is None
        assert data["recent_records"] == []


class TestPrintingPrescriptions:
    def test_nurse_reprints_a_prescription_without_the_note(
        self, seed, client, nurse_headers
    ):
        from datetime import date

        from medicore.domain.entities.prescription import PrescriptionSnapshot

        record = store_record(seed, code="REC-RX", encounter_at=datetime(2026, 5, 20, 9))
        seed.factory.store.medical_records[record.id.value] = type(record)(
            **{
                **{f: getattr(record, f) for f in record.__dataclass_fields__},
                "prescriptions": (
                    PrescriptionSnapshot("Paracetamol", "500 mg", "c/8 h", date(2026, 5, 20)),
                ),
            }
        )
        resp = client.get(f"/api/v1/print/records/{record.id}", headers=nurse_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["document"] == "prescription"
        assert body["indications"] is None
        assert set(body["record"]) == {
            "id", "code", "encounter_at", "status", "prescriptions", "signed_by_id",
            "amends_record_id",
        }
        exams = client.get(
            f"/api/v1/print/records/{record.id}?document=record", headers=nurse_headers
        )
        assert exams.status_code == 403
