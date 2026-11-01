"""Patients list support: filtered/accent-insensitive search, last visits and page stats."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from medicore.application.use_cases.patients import (
    GetPatientStats,
    PatientsLastVisits,
    SearchPatients,
)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType, PatientStatus
from medicore.domain.repositories._support import PatientFilter
from medicore.domain.shared.identifiers import AppointmentId, PatientId
from medicore.domain.value_objects.contact_info import ContactInfo
from tests.support.builders import build_patient, seed_clinic
from tests.support.fakes import FixedClock

NOW = datetime(2026, 5, 31, 9, 0)  # FixedClock default


def _patient(seed, code: str, first: str, last: str, **kw):
    p = build_patient(seed.tenant.id, code=code, first_name=first, last_name=last, **kw)
    seed.factory.for_tenant(seed.tenant.id).patients.save(p)
    return p


def _appt(seed, pid: PatientId, start: datetime, status: AppointmentStatus) -> None:
    seed.factory.for_tenant(seed.tenant.id).appointments.save(
        Appointment(
            id=AppointmentId.new(),
            tenant_id=seed.tenant.id,
            code="A-0000",
            patient_id=pid,
            doctor_id=seed.doctor.id,
            location_id=seed.tenant.primary_location.id,
            type=AppointmentType.CONSULT,
            scheduled_start=start,
            duration_minutes=30,
            reason="Control",
            created_by_id=seed.receptionist.id,
            status=status,
        )
    )


def _search(seed, q: str, f: PatientFilter | None = None) -> list[str]:
    uow = seed.factory.for_tenant(seed.tenant.id)
    return [p.code for p in SearchPatients(uow).execute(seed.doctor_actor, q, None, f).items]


def test_search_ignores_accents_and_case_both_ways():
    seed = seed_clinic()
    _patient(seed, "P-00201", "Rosa", "Álvarez Díaz")
    _patient(seed, "P-00202", "Ramon", "Nunez")

    assert _search(seed, "alvarez") == ["P-00201"]
    assert _search(seed, "ÁLVAREZ") == ["P-00201"]
    assert _search(seed, "Ramón Núñez") == ["P-00202"]


def test_search_matches_every_word_in_any_order():
    seed = seed_clinic()
    _patient(seed, "P-00201", "Rosa", "Álvarez Díaz")
    _patient(seed, "P-00202", "Rosa", "Martínez")

    assert _search(seed, "rosa alvarez") == ["P-00201"]
    assert _search(seed, "diaz rosa") == ["P-00201"]
    assert sorted(_search(seed, "rosa")) == ["P-00201", "P-00202"]


def test_search_by_phone_digits_ignoring_formatting():
    seed = seed_clinic()
    _patient(seed, "P-00201", "Ana", "Ruiz", contact=ContactInfo(phone="+503 7123-4567"))

    assert _search(seed, "71234567") == ["P-00201"]
    assert _search(seed, "7123-45") == ["P-00201"]
    assert _search(seed, "99999") == []


def test_search_honours_the_status_filter():
    seed = seed_clinic()
    _patient(seed, "P-00201", "Rosa", "Activa")
    _patient(seed, "P-00202", "Rosa", "Archivada", status=PatientStatus.INACTIVE)

    assert _search(seed, "rosa", PatientFilter(status="inactive")) == ["P-00202"]
    assert _search(seed, "rosa", PatientFilter(status="active")) == ["P-00201"]


def test_last_visit_is_the_latest_completed_appointment():
    seed = seed_clinic()
    pid = seed.patient.id
    _appt(seed, pid, datetime(2026, 4, 1, 10, 0), AppointmentStatus.COMPLETED)
    _appt(seed, pid, datetime(2026, 5, 20, 10, 0), AppointmentStatus.COMPLETED)  # latest
    _appt(seed, pid, datetime(2026, 5, 25, 10, 0), AppointmentStatus.NO_SHOW)  # not a visit
    _appt(seed, pid, datetime(2026, 6, 5, 10, 0), AppointmentStatus.CONFIRMED)  # ahead
    other = _patient(seed, "P-00201", "Sin", "Visitas")
    uow = seed.factory.for_tenant(seed.tenant.id)

    visits = PatientsLastVisits(uow).execute(seed.doctor_actor, [pid, other.id])

    assert visits == {pid: datetime(2026, 5, 20, 10, 0)}


def test_stats_count_status_recent_registrations_and_upcoming():
    seed = seed_clinic()
    old = datetime(2025, 1, 1, tzinfo=UTC)
    seed.patient.created_at = old
    seed.factory.for_tenant(seed.tenant.id).patients.save(seed.patient)
    recent = _patient(
        seed, "P-00201", "Nueva", "Paciente", created_at=datetime(2026, 5, 20, tzinfo=UTC)
    )
    _patient(seed, "P-00202", "Baja", "Paciente", status=PatientStatus.INACTIVE, created_at=old)
    _appt(seed, recent.id, NOW + timedelta(days=3), AppointmentStatus.SCHEDULED)
    _appt(seed, recent.id, NOW + timedelta(days=9), AppointmentStatus.CONFIRMED)  # same patient
    _appt(seed, seed.patient.id, NOW - timedelta(days=3), AppointmentStatus.SCHEDULED)  # past
    uow = seed.factory.for_tenant(seed.tenant.id)

    stats = GetPatientStats(uow, FixedClock(NOW)).execute(seed.receptionist_actor)

    assert (stats.active, stats.inactive) == (2, 1)
    assert stats.new_recent == 1
    assert stats.with_upcoming == 1
