"""Tests for the prescription lifecycle use cases."""

from __future__ import annotations

from datetime import date

import pytest

from medicore.application.use_cases.patients import GetPatientDetail
from medicore.application.use_cases.prescriptions import (
    CancelPrescription,
    CompletePrescription,
    ListPatientPrescriptions,
)
from medicore.domain.entities.prescription import Prescription
from medicore.domain.enums import PrescriptionStatus
from medicore.domain.shared.errors import InvalidStateTransition, PermissionDenied
from medicore.domain.shared.identifiers import PrescriptionId
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock


def issue(seed, uow, *, end_date: date | None = None, drug: str = "Enalapril") -> Prescription:
    """Persist a prescription as if it had been issued by signing a consultation."""
    rx = Prescription(
        id=PrescriptionId.new(),
        tenant_id=seed.tenant.id,
        patient_id=seed.patient.id,
        prescriber_id=seed.doctor.id,
        drug=drug,
        dose="20 mg",
        schedule="1× día",
        start_date=date(2026, 5, 1),
        end_date=end_date,
    )
    uow.prescriptions.save(rx)
    return rx


class TestLifecycle:
    def test_doctor_completes_prescription(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)

        done = CompletePrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id)

        assert done.status == PrescriptionStatus.COMPLETED
        assert uow.prescriptions.get_by_id(rx.id).status == PrescriptionStatus.COMPLETED
        assert uow.audit.query(action="prescription.completed")

    def test_doctor_cancels_prescription(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)

        CancelPrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id)

        assert uow.prescriptions.get_by_id(rx.id).status == PrescriptionStatus.CANCELLED
        assert uow.audit.query(action="prescription.cancelled")

    def test_complete_cancelled_rejected(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        CancelPrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id)
        with pytest.raises(InvalidStateTransition):
            CompletePrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id)

    def test_nurse_cannot_manage_prescriptions(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        with pytest.raises(PermissionDenied):
            CompletePrescription(uow, FixedClock()).execute(seed.actor(seed.nurse), rx.id)
        with pytest.raises(PermissionDenied):
            CancelPrescription(uow, FixedClock()).execute(seed.receptionist_actor, rx.id)


class TestListing:
    def test_list_returns_all_statuses_with_prescriber_name(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        active = issue(seed, uow, drug="Enalapril")
        completed = issue(seed, uow, drug="Ibuprofeno")
        CompletePrescription(uow, FixedClock()).execute(seed.doctor_actor, completed.id)

        views = ListPatientPrescriptions(uow).execute(seed.actor(seed.nurse), seed.patient.id)

        assert {v.prescription.id for v in views} == {active.id, completed.id}
        assert all(v.prescriber_name == seed.doctor.name for v in views)

    def test_receptionist_cannot_list(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            ListPatientPrescriptions(uow).execute(seed.receptionist_actor, seed.patient.id)


class TestActiveCount:
    def test_expired_prescription_does_not_count_as_active(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        issue(seed, uow, drug="Vigente")  # indefinite → counts
        issue(seed, uow, drug="Vencida", end_date=date(2026, 5, 20))  # before the fixed clock

        detail = GetPatientDetail(uow, FixedClock()).execute(seed.doctor_actor, seed.patient.id)

        assert detail.active_prescriptions == 1
