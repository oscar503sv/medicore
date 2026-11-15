"""Tests for the consultation lifecycle: start, edit, and the atomic sign transaction."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
)
from medicore.application.use_cases.consultations import (
    AddDiagnosis,
    AddPrescriptionDraft,
    AutosaveConsultation,
    ConsultationPatch,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    ConsultationStatus,
    PrescriptionStatus,
    RecordStatus,
)
from medicore.domain.shared.errors import (
    ConsultationAlreadySigned,
    ConsultationNotSignable,
    PermissionDenied,
)
from medicore.domain.value_objects.icd_code import IcdCode
from tests.support.builders import seed_clinic, soap_note
from tests.support.fakes import FixedClock, SequentialCodeGenerator

MONDAY_9AM = datetime(2026, 6, 1, 9, 0)


def booked(seed, uow):
    """Create a scheduled appointment for the seed's doctor + patient."""
    create = CreateAppointment(uow, SequentialCodeGenerator(), FixedClock())
    return create.execute(
        seed.doctor_actor,
        CreateAppointmentCommand(
            patient_id=seed.patient.id,
            doctor_id=seed.doctor.id,
            location_id=seed.tenant.primary_location.id,
            type=AppointmentType.CONSULT,
            scheduled_start=MONDAY_9AM,
            reason="Control de tensión",
        ),
    )


def fill(seed, uow, consultation):
    clock = FixedClock()
    AutosaveConsultation(uow, clock).execute(
        seed.doctor_actor,
        consultation.id,
        ConsultationPatch(
            note=soap_note("subjetivo", "objetivo", "evaluación", "plan").texts(),
            vitals={"heart_rate": 72, "weight": Decimal("70")},
        ),
    )
    AddDiagnosis(uow, clock).execute(
        seed.doctor_actor, consultation.id, IcdCode("I10", "Hipertensión")
    )


def test_start_consultation_moves_appointment_in_progress():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)

    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)

    assert consultation.status == ConsultationStatus.DRAFT
    assert uow.appointments.get_by_id(appt.id).status == AppointmentStatus.IN_PROGRESS
    assert uow.audit.query(action="consultation.started")


def test_start_consultation_is_idempotent():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)
    start = StartConsultation(uow, FixedClock())
    first = start.execute(seed.doctor_actor, appt.id)
    second = start.execute(seed.doctor_actor, appt.id)
    assert first.id == second.id


def test_sign_consultation_is_atomic_and_complete():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    fill(seed, uow, consultation)
    AddPrescriptionDraft(uow, FixedClock()).execute(
        seed.doctor_actor,
        consultation.id,
        PrescriptionDraft(drug="Enalapril", dose="20 mg", schedule="1× día", duration_days=30),
    )

    record = SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor,
        SignConsultationCommand(consultation_id=consultation.id),
    )

    # immutable record created
    assert record.status == RecordStatus.SIGNED
    assert record.code.startswith("REC-")
    assert record.location_name == "Madrid · Atocha"
    assert uow.medical_records.get_by_id(record.id) is not None
    # appointment completed
    assert uow.appointments.get_by_id(appt.id).status == AppointmentStatus.COMPLETED
    # prescription issued and active, linked to the record
    prescriptions = uow.prescriptions.list_by_patient(seed.patient.id)
    assert len(prescriptions) == 1
    assert prescriptions[0].status == PrescriptionStatus.ACTIVE
    assert prescriptions[0].record_id == record.id
    # consultation signed + audited
    assert uow.consultations.get_by_id(consultation.id).status == ConsultationStatus.SIGNED
    assert uow.audit.query(action="consultation.signed")


def test_sign_incomplete_consultation_rolls_back_everything():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    # only a tiny bit of content → below the sign threshold
    AutosaveConsultation(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id, ConsultationPatch(note={"subjective": "x"})
    )

    with pytest.raises(ConsultationNotSignable):
        SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
            seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id)
        )

    # nothing leaked: no record, appointment still in_progress, consultation still draft
    assert uow.medical_records.list_by_patient(seed.patient.id) == []
    assert uow.appointments.get_by_id(appt.id).status == AppointmentStatus.IN_PROGRESS
    assert uow.consultations.get_by_id(consultation.id).status == ConsultationStatus.DRAFT


def test_nurse_cannot_sign():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    fill(seed, uow, consultation)

    with pytest.raises(PermissionDenied):
        SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
            seed.actor(seed.nurse), SignConsultationCommand(consultation_id=consultation.id)
        )


def _signable(seed, uow):
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    fill(seed, uow, consultation)
    return appt, consultation


def _sign(seed, uow, consultation):
    return SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id)
    )


def test_sign_locks_the_consultation():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    _, consultation = _signable(seed, uow)
    seed.factory.store.consultation_locks.clear()

    _sign(seed, uow, consultation)

    assert seed.factory.store.consultation_locks == {consultation.id.value: 1}


def test_second_sign_is_refused_and_writes_nothing():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    _, consultation = _signable(seed, uow)
    AddPrescriptionDraft(uow, FixedClock()).execute(
        seed.doctor_actor,
        consultation.id,
        PrescriptionDraft(drug="Enalapril", dose="20 mg", schedule="1× día", duration_days=30),
    )
    _sign(seed, uow, consultation)

    with pytest.raises(ConsultationAlreadySigned):
        _sign(seed, uow, consultation)

    assert len(uow.medical_records.list_by_patient(seed.patient.id)) == 1
    assert len(uow.prescriptions.list_by_patient(seed.patient.id)) == 1
    assert len(uow.audit.query(action="consultation.signed")) == 1


def test_failed_sign_releases_nothing_persistent():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    seed.factory.store.consultation_locks.clear()

    with pytest.raises(ConsultationNotSignable):
        _sign(seed, uow, consultation)

    assert seed.factory.store.consultation_locks == {}


def test_edit_after_sign_is_refused():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    _, consultation = _signable(seed, uow)
    _sign(seed, uow, consultation)

    with pytest.raises(ConsultationAlreadySigned):
        AutosaveConsultation(uow, FixedClock()).execute(
            seed.doctor_actor, consultation.id, ConsultationPatch(note={"plan": "late"})
        )

    assert uow.consultations.get_by_id(consultation.id).status == ConsultationStatus.SIGNED


def test_editors_lock_the_consultation():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)
    consultation = StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, appt.id)
    locks = seed.factory.store.consultation_locks
    locks.clear()

    AutosaveConsultation(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id, ConsultationPatch(note={"plan": "p"})
    )
    AddDiagnosis(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id, IcdCode("I10", "Hipertensión")
    )

    assert locks == {consultation.id.value: 2}


def test_start_locks_the_appointment_and_returns_the_same_consultation():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)
    appt = booked(seed, uow)
    start = StartConsultation(uow, FixedClock())

    first = start.execute(seed.doctor_actor, appt.id)
    assert seed.factory.store.appointment_locks == {appt.id.value: 1}
    second = start.execute(seed.doctor_actor, appt.id)

    assert first.id == second.id
    # the second start returns without committing, so the fake rolls its lock back
    assert seed.factory.store.appointment_locks == {appt.id.value: 1}
    assert len(seed.factory.store.consultations) == 1
