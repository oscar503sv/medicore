"""The records list: metadata only, filtered and paginated on the server, and audited."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.records import (
    MAX_RECORDS_PAGE,
    ListMedicalRecords,
    RecordQuery,
)
from medicore.domain.enums import ClinicalRecordType
from medicore.domain.repositories._support import Paging, RecordSummary
from medicore.domain.shared.errors import PermissionDenied
from tests.support.builders import build_patient, seed_clinic
from tests.support.fakes import FixedClock
from tests.support.records import store_record


@pytest.fixture
def seed():
    return seed_clinic()


def _list(seed, actor, query=None, paging=None) -> object:
    uow = seed.factory.for_tenant(seed.tenant.id)
    return ListMedicalRecords(uow, FixedClock()).execute(
        actor, query or RecordQuery(), paging or Paging()
    )


def _other_patient(seed, **overrides):
    patient = build_patient(seed.tenant.id, code="P-00200", **overrides)
    seed.factory.store.patients[patient.id.value] = patient
    return patient


class TestWhoSeesWhat:
    def test_doctor_admin_and_nurse_get_summaries_without_clinical_content(self, seed):
        store_record(seed, code="REC-1", encounter_at=datetime(2026, 5, 20, 9))
        for actor in (seed.doctor_actor, seed.actor(seed.admin), seed.actor(seed.nurse)):
            page = _list(seed, actor)
            assert page.total == 1
            summary = page.items[0]
            assert isinstance(summary, RecordSummary)
            assert summary.patient_name == seed.patient.full_name
            assert summary.signed_by_name == seed.doctor.name
            assert not hasattr(summary, "note")
            assert not hasattr(summary, "chief_complaint")

    def test_receptionist_is_denied(self, seed):
        with pytest.raises(PermissionDenied):
            _list(seed, seed.receptionist_actor)


class TestFilteringAndPaging:
    def test_pages_newest_first_and_reports_the_total(self, seed):
        for day in range(1, 6):
            store_record(seed, code=f"REC-{day}", encounter_at=datetime(2026, 5, day, 9))
        page = _list(seed, seed.doctor_actor, paging=Paging(offset=1, limit=2))
        assert [s.code for s in page.items] == ["REC-4", "REC-3"]
        assert (page.total, page.offset, page.limit) == (5, 1, 2)

    def test_limit_is_clamped(self, seed):
        page = _list(seed, seed.doctor_actor, paging=Paging(limit=10_000))
        assert page.limit == MAX_RECORDS_PAGE

    def test_filters_by_patient_and_type(self, seed):
        other = _other_patient(seed)
        store_record(seed, code="REC-A", encounter_at=datetime(2026, 5, 1, 9))
        store_record(seed, code="REC-B", encounter_at=datetime(2026, 5, 2, 9), patient=other)
        store_record(
            seed, code="REC-C", encounter_at=datetime(2026, 5, 3, 9),
            type=ClinicalRecordType.PROCEDURE,
        )
        by_patient = _list(seed, seed.doctor_actor, RecordQuery(patient_id=other.id))
        assert [s.code for s in by_patient.items] == ["REC-B"]
        by_type = _list(
            seed, seed.doctor_actor, RecordQuery(type=ClinicalRecordType.PROCEDURE)
        )
        assert [s.code for s in by_type.items] == ["REC-C"]

    def test_date_range_includes_the_whole_last_day(self, seed):
        store_record(seed, code="IN-LATE", encounter_at=datetime(2026, 5, 20, 23, 30))
        store_record(seed, code="IN-EARLY", encounter_at=datetime(2026, 5, 10, 0, 0))
        store_record(seed, code="OUT-AFTER", encounter_at=datetime(2026, 5, 21, 0, 0))
        store_record(seed, code="OUT-BEFORE", encounter_at=datetime(2026, 5, 9, 23, 59))
        page = _list(
            seed, seed.doctor_actor,
            RecordQuery(date_from=date(2026, 5, 10), date_to=date(2026, 5, 20)),
        )
        assert {s.code for s in page.items} == {"IN-LATE", "IN-EARLY"}

    def test_inverted_range_is_rejected(self, seed):
        with pytest.raises(ValidationError) as exc:
            _list(
                seed, seed.doctor_actor,
                RecordQuery(date_from=date(2026, 5, 20), date_to=date(2026, 5, 10)),
            )
        assert exc.value.code == "records.invalid_range"

    def test_search_by_record_code_and_by_patient_name_without_accents(self, seed):
        other = _other_patient(seed, first_name="José", last_name="Núñez")
        store_record(seed, code="REC-2026-0001", encounter_at=datetime(2026, 5, 1, 9))
        store_record(
            seed, code="REC-2026-0002", encounter_at=datetime(2026, 5, 2, 9), patient=other
        )
        by_code = _list(seed, seed.doctor_actor, RecordQuery(search="0001"))
        assert [s.code for s in by_code.items] == ["REC-2026-0001"]
        by_name = _list(seed, seed.doctor_actor, RecordQuery(search="jose nunez"))
        assert [s.code for s in by_name.items] == ["REC-2026-0002"]
        by_patient_code = _list(seed, seed.doctor_actor, RecordQuery(search="p-00200"))
        assert [s.code for s in by_patient_code.items] == ["REC-2026-0002"]

    def test_the_chief_complaint_is_not_searchable(self, seed):
        store_record(
            seed, code="REC-1", encounter_at=datetime(2026, 5, 1, 9),
            chief_complaint="dolor torácico",
        )
        assert _list(seed, seed.doctor_actor, RecordQuery(search="torácico")).total == 0


class TestAudit:
    def test_listing_is_audited_without_the_search_text(self, seed):
        store_record(seed, code="REC-1", encounter_at=datetime(2026, 5, 1, 9))
        _list(seed, seed.actor(seed.admin), RecordQuery(search="Lucía"))
        entry = seed.factory.for_tenant(seed.tenant.id).audit.query(action="record.listed")[0]
        assert entry.entity_type == "MedicalRecord"
        assert entry.metadata["searched"] is True
        assert entry.metadata["returned"] == 1
        assert "Lucía" not in str(entry.metadata)

    def test_a_patient_filter_names_the_patient_in_the_entry(self, seed):
        store_record(seed, code="REC-1", encounter_at=datetime(2026, 5, 1, 9))
        _list(seed, seed.doctor_actor, RecordQuery(patient_id=seed.patient.id))
        entry = seed.factory.for_tenant(seed.tenant.id).audit.query(action="record.listed")[0]
        assert (entry.entity_type, entry.entity_id) == ("Patient", str(seed.patient.id))
        assert entry.metadata["subject"] == f"{seed.patient.code} · {seed.patient.full_name}"
        assert entry.metadata["total"] == 1
