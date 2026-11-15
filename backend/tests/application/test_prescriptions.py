"""Tests for the prescription lifecycle use cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from medicore.application.common.errors import EntityNotFound
from medicore.application.use_cases.patients import GetPatientDetail
from medicore.application.use_cases.prescriptions import (
    CancelPrescription,
    CompletePrescription,
    ListPatientPrescriptions,
)
from medicore.domain.entities.prescription import Prescription
from medicore.domain.enums import PrescriptionStatus, Role
from medicore.domain.shared.errors import (
    InvalidStateTransition,
    InvalidValueObject,
    PermissionDenied,
)
from medicore.domain.shared.identifiers import PlatformAdminId, PrescriptionId
from tests.support.builders import build_user, seed_clinic
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


REASON = "Patient developed a rash after the first doses"


def _other_doctor(seed):
    doctor = build_user(seed.tenant.id, Role.DOCTOR, email="other@clinica-norte.test")
    seed.factory.store.users[doctor.id.value] = doctor
    return seed.actor(doctor)


class TestLifecycle:
    def test_prescriber_completes_prescription(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)

        done = CompletePrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id)

        saved = uow.prescriptions.get_by_id(rx.id)
        assert done.status == saved.status == PrescriptionStatus.COMPLETED
        assert saved.closed_by_id == seed.doctor.id and saved.closed_at is not None
        assert uow.audit.query(action="prescription.completed")

    def test_prescriber_cancels_prescription_with_a_reason(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)

        CancelPrescription(uow, FixedClock()).execute(
            seed.doctor_actor, rx.id, reason=f"  {REASON} "
        )

        saved = uow.prescriptions.get_by_id(rx.id)
        assert saved.status == PrescriptionStatus.CANCELLED
        assert saved.cancel_reason == REASON
        assert saved.closed_by_id == seed.doctor.id and saved.closed_at is not None

    def test_audit_keeps_the_reason_length_but_never_its_text(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)

        CancelPrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id, reason=REASON)

        (entry,) = uow.audit.query(action="prescription.cancelled")
        assert entry.metadata["reason_chars"] == len(REASON)
        assert all(REASON not in str(v) for v in entry.metadata.values())

    def test_cancel_with_a_short_reason_changes_nothing(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)

        with pytest.raises(InvalidValueObject) as exc:
            CancelPrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id, reason="short")

        assert exc.value.code == "prescription.cancel_reason_invalid"
        assert uow.prescriptions.get_by_id(rx.id).status == PrescriptionStatus.ACTIVE
        assert not uow.audit.query(action="prescription.cancelled")

    def test_another_doctor_cannot_close_it(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        other = _other_doctor(seed)

        with pytest.raises(PermissionDenied) as complete_exc:
            CompletePrescription(uow, FixedClock()).execute(other, rx.id)
        with pytest.raises(PermissionDenied) as cancel_exc:
            CancelPrescription(uow, FixedClock()).execute(other, rx.id, reason=REASON)

        assert complete_exc.value.code == cancel_exc.value.code == "prescription.not_own"
        assert uow.prescriptions.get_by_id(rx.id).status == PrescriptionStatus.ACTIVE

    def test_closing_again_is_an_invalid_transition(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        CancelPrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id, reason=REASON)
        with pytest.raises(InvalidStateTransition):
            CompletePrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id)
        with pytest.raises(InvalidStateTransition):
            CancelPrescription(uow, FixedClock()).execute(
                seed.doctor_actor, rx.id, reason=REASON
            )

    def test_unknown_prescription_is_not_found(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(EntityNotFound):
            CompletePrescription(uow, FixedClock()).execute(
                seed.doctor_actor, PrescriptionId.new()
            )

    def test_nurse_and_receptionist_cannot_manage_prescriptions(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        with pytest.raises(PermissionDenied) as exc:
            CompletePrescription(uow, FixedClock()).execute(seed.actor(seed.nurse), rx.id)
        assert exc.value.code == "permission.missing"
        with pytest.raises(PermissionDenied):
            CancelPrescription(uow, FixedClock()).execute(
                seed.receptionist_actor, rx.id, reason=REASON
            )
        assert uow.prescriptions.get_by_id(rx.id).status == PrescriptionStatus.ACTIVE

    def test_support_sessions_cannot_close_prescriptions(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        support = replace(seed.doctor_actor, impersonated_by=PlatformAdminId.new())
        with pytest.raises(PermissionDenied) as exc:
            CompletePrescription(uow, FixedClock()).execute(support, rx.id)
        assert exc.value.code == "support.clinical_forbidden"

    def test_closing_notifies_nobody(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        CancelPrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id, reason=REASON)
        assert not seed.factory.store.notifications


class TestListing:
    def test_list_returns_all_statuses_with_prescriber_name(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        active = issue(seed, uow, drug="Enalapril")
        completed = issue(seed, uow, drug="Ibuprofeno")
        CompletePrescription(uow, FixedClock()).execute(seed.doctor_actor, completed.id)

        views = ListPatientPrescriptions(uow, FixedClock()).execute(
            seed.actor(seed.nurse), seed.patient.id
        )

        assert {v.prescription.id for v in views} == {active.id, completed.id}
        assert all(v.prescriber_name == seed.doctor.name for v in views)

    def test_cancel_reason_only_reaches_who_reads_clinical_content(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        rx = issue(seed, uow)
        CancelPrescription(uow, FixedClock()).execute(seed.doctor_actor, rx.id, reason=REASON)
        listing = ListPatientPrescriptions(uow, FixedClock())

        (as_doctor,) = listing.execute(seed.doctor_actor, seed.patient.id)
        (as_nurse,) = listing.execute(seed.actor(seed.nurse), seed.patient.id)

        assert as_doctor.cancel_reason == REASON
        assert as_nurse.cancel_reason is None
        assert as_nurse.prescription.status == PrescriptionStatus.CANCELLED

    def test_receptionist_cannot_list(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            ListPatientPrescriptions(uow, FixedClock()).execute(
                seed.receptionist_actor, seed.patient.id
            )


class TestActiveCount:
    def test_expired_prescription_does_not_count_as_active(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        issue(seed, uow, drug="Vigente")  # indefinite → counts
        issue(seed, uow, drug="Vencida", end_date=date(2026, 5, 20))  # before the fixed clock

        detail = GetPatientDetail(uow, FixedClock()).execute(seed.doctor_actor, seed.patient.id)

        assert detail.active_prescriptions == 1
