"""Tests for the per-patient next-visit lookup used to enrich the patients list."""

from __future__ import annotations

from datetime import UTC, datetime

from medicore.application.use_cases.patients import PatientsNextVisits
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType
from medicore.domain.shared.identifiers import AppointmentId, PatientId
from tests.support.builders import build_patient, seed_clinic
from tests.support.fakes import FixedClock

NOW = datetime(2026, 5, 31, 9, 0)  # FixedClock default


def _appt(seed, patient_id: PatientId, start: datetime, status: AppointmentStatus) -> Appointment:
    return Appointment(
        id=AppointmentId.new(),
        tenant_id=seed.tenant.id,
        code="A-0000",
        patient_id=patient_id,
        doctor_id=seed.doctor.id,
        location_id=seed.tenant.primary_location.id,
        type=AppointmentType.CONSULT,
        scheduled_start=start,
        duration_minutes=30,
        reason="Control",
        created_by_id=seed.receptionist.id,
        status=status,
    )


def _save(seed, *appointments: Appointment) -> None:
    uow = seed.factory.for_tenant(seed.tenant.id)
    for a in appointments:
        uow.appointments.save(a)


def test_returns_earliest_active_future_appointment():
    seed = seed_clinic()
    pid = seed.patient.id
    _save(
        seed,
        _appt(seed, pid, datetime(2026, 5, 20, 10, 0), AppointmentStatus.COMPLETED),  # past
        _appt(seed, pid, datetime(2026, 6, 10, 10, 0), AppointmentStatus.CONFIRMED),  # later
        _appt(seed, pid, datetime(2026, 6, 5, 10, 0), AppointmentStatus.SCHEDULED),  # earliest
        _appt(seed, pid, datetime(2026, 6, 2, 10, 0), AppointmentStatus.CANCELLED),  # not active
    )
    uow = seed.factory.for_tenant(seed.tenant.id)

    visits = PatientsNextVisits(uow, FixedClock(NOW)).execute(seed.doctor_actor, [pid])

    assert visits == {pid: datetime(2026, 6, 5, 10, 0)}


def test_patient_without_upcoming_is_omitted():
    seed = seed_clinic()
    pid = seed.patient.id
    _save(
        seed,
        _appt(seed, pid, datetime(2026, 5, 20, 10, 0), AppointmentStatus.COMPLETED),
        _appt(seed, pid, datetime(2026, 6, 2, 10, 0), AppointmentStatus.CANCELLED),
    )
    uow = seed.factory.for_tenant(seed.tenant.id)

    visits = PatientsNextVisits(uow, FixedClock(NOW)).execute(seed.doctor_actor, [pid])

    assert visits == {}


def test_maps_each_patient_independently():
    seed = seed_clinic()
    other = build_patient(seed.tenant.id, code="P-00200")
    seed.factory.store.patients[other.id.value] = other
    _save(
        seed,
        _appt(seed, seed.patient.id, datetime(2026, 6, 5, 10, 0), AppointmentStatus.SCHEDULED),
        _appt(seed, other.id, datetime(2026, 6, 7, 12, 0), AppointmentStatus.SCHEDULED),
    )
    uow = seed.factory.for_tenant(seed.tenant.id)

    visits = PatientsNextVisits(uow, FixedClock(NOW)).execute(
        seed.doctor_actor, [seed.patient.id, other.id]
    )

    assert visits == {
        seed.patient.id: datetime(2026, 6, 5, 10, 0),
        other.id: datetime(2026, 6, 7, 12, 0),
    }


def test_empty_patient_list_returns_empty():
    seed = seed_clinic()
    uow = seed.factory.for_tenant(seed.tenant.id)

    assert PatientsNextVisits(uow, FixedClock(NOW)).execute(seed.doctor_actor, []) == {}


def test_now_is_compared_in_clinic_timezone():
    """Regression: a tz-aware UTC clock must be converted to the clinic wall-clock before
    comparing. A clinic behind UTC was wrongly hiding later-today appointments."""
    seed = seed_clinic()
    seed.tenant.timezone = "America/Mexico_City"  # UTC-6, no DST
    pid = seed.patient.id
    # Appointment today at 17:00 clinic-local. "Now" is 21:00 UTC == 15:00 clinic-local,
    # so 17:00 is still in the future and must appear.
    _save(seed, _appt(seed, pid, datetime(2026, 6, 3, 17, 0), AppointmentStatus.SCHEDULED))
    uow = seed.factory.for_tenant(seed.tenant.id)
    clock = FixedClock(datetime(2026, 6, 3, 21, 0, tzinfo=UTC))

    visits = PatientsNextVisits(uow, clock).execute(seed.doctor_actor, [pid])

    assert visits == {pid: datetime(2026, 6, 3, 17, 0)}
