"""A patient's history, vitals, prescriptions and documents: who may open what, and the trail."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from medicore.application.common.errors import EntityNotFound
from medicore.application.use_cases.patients import GetPatientDetail
from medicore.application.use_cases.prescriptions import ListPatientPrescriptions
from medicore.application.use_cases.records import (
    ListPatientDocuments,
    ListPatientHistory,
    ListPatientVitals,
)
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import PatientId
from medicore.domain.value_objects.vitals import Vitals
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock
from tests.support.records import store_record


@pytest.fixture
def seed():
    s = seed_clinic()
    store_record(
        s, code="REC-OLD", encounter_at=datetime(2026, 4, 1, 9),
        vitals=Vitals(heart_rate=80),
    )
    store_record(s, code="REC-NO-VITALS", encounter_at=datetime(2026, 5, 1, 9))
    store_record(
        s, code="REC-NEW", encounter_at=datetime(2026, 5, 20, 9),
        vitals=Vitals(weight=Decimal("70")),
    )
    return s


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _actions(seed, action):
    return _uow(seed).audit.query(action=action)


class TestHistory:
    def test_the_doctor_reads_it_and_it_is_audited_with_a_count(self, seed):
        records = ListPatientHistory(_uow(seed), FixedClock()).execute(
            seed.doctor_actor, seed.patient.id
        )
        assert [r.code for r in records] == ["REC-NEW", "REC-NO-VITALS", "REC-OLD"]
        entry = _actions(seed, "record.history_viewed")[0]
        assert entry.metadata["count"] == 3
        assert entry.metadata["subject"] == f"{seed.patient.code} · {seed.patient.full_name}"

    @pytest.mark.parametrize("who", ["admin", "nurse"])
    def test_staff_without_the_clinical_permission_are_denied(self, seed, who):
        with pytest.raises(PermissionDenied) as exc:
            ListPatientHistory(_uow(seed), FixedClock()).execute(
                seed.actor(getattr(seed, who)), seed.patient.id
            )
        assert exc.value.code == "permission.missing"
        assert not _actions(seed, "record.history_viewed")

    def test_receptionist_is_denied(self, seed):
        with pytest.raises(PermissionDenied):
            ListPatientHistory(_uow(seed), FixedClock()).execute(
                seed.receptionist_actor, seed.patient.id
            )

    def test_unknown_patient_is_not_found(self, seed):
        with pytest.raises(EntityNotFound):
            ListPatientHistory(_uow(seed), FixedClock()).execute(
                seed.doctor_actor, PatientId.new()
            )


class TestVitals:
    @pytest.mark.parametrize("who", ["admin", "nurse"])
    def test_only_the_readings_with_vitals_newest_first(self, seed, who):
        readings = ListPatientVitals(_uow(seed), FixedClock()).execute(
            seed.actor(getattr(seed, who)), seed.patient.id
        )
        assert [r.record_code for r in readings] == ["REC-NEW", "REC-OLD"]
        assert readings[0].vitals.weight == Decimal("70")
        assert _actions(seed, "patient.vitals_listed")[-1].metadata["count"] == 2

    def test_receptionist_is_denied(self, seed):
        with pytest.raises(PermissionDenied):
            ListPatientVitals(_uow(seed), FixedClock()).execute(
                seed.receptionist_actor, seed.patient.id
            )


class TestListingsAreAudited:
    def test_prescriptions_and_documents_leave_a_trail_and_stay_open_to_nursing(self, seed):
        nurse = seed.actor(seed.nurse)
        ListPatientPrescriptions(_uow(seed), FixedClock()).execute(nurse, seed.patient.id)
        ListPatientDocuments(_uow(seed), FixedClock()).execute(nurse, seed.patient.id)
        assert _actions(seed, "prescription.listed")[0].metadata["count"] == 0
        assert _actions(seed, "document.listed")[0].metadata["count"] == 0
        assert _actions(seed, "document.listed")[0].entity_id == str(seed.patient.id)


class TestPatientDetail:
    @pytest.mark.parametrize("who", ["admin", "nurse"])
    def test_carries_the_latest_vitals_and_recent_records_without_content(self, seed, who):
        detail = GetPatientDetail(_uow(seed), FixedClock()).execute(
            seed.actor(getattr(seed, who)), seed.patient.id
        )
        assert detail.latest_vitals.record_code == "REC-NEW"
        assert [r.code for r in detail.recent_records] == ["REC-NEW", "REC-NO-VITALS", "REC-OLD"]
        assert not hasattr(detail.recent_records[0], "chief_complaint")

    def test_reception_gets_neither(self, seed):
        detail = GetPatientDetail(_uow(seed), FixedClock()).execute(
            seed.receptionist_actor, seed.patient.id
        )
        assert detail.latest_vitals is None
        assert detail.recent_records == []

    def test_still_a_single_chart_entry(self, seed):
        GetPatientDetail(_uow(seed), FixedClock()).execute(seed.actor(seed.nurse), seed.patient.id)
        assert len(_actions(seed, "patient.chart_viewed")) == 1
        assert not _actions(seed, "record.listed")
