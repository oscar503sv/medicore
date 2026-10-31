"""Tests for the dashboard summary metrics."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from medicore.application.use_cases.dashboard import GetDashboardSummary
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType, Role
from medicore.domain.shared.identifiers import AppointmentId
from tests.support.builders import (
    build_patient,
    build_user,
    build_weekday_availability,
    seed_clinic,
)
from tests.support.fakes import FixedClock

MONDAY = date(2026, 6, 8)
LAST_MONDAY = MONDAY - timedelta(days=7)
CLOCK = FixedClock(datetime(2026, 6, 8, 8, 0))  # Monday morning, clinic wall-clock
# The seeded doctor works Mon–Fri 09:00–13:00 in 30-minute slots → 8 bookable slots a day.


def _appt(seed, doctor, day: date, hour: int, minute: int = 0, status=AppointmentStatus.SCHEDULED):
    a = Appointment(
        id=AppointmentId.new(),
        tenant_id=seed.tenant.id,
        code=f"A-{len(seed.factory.store.appointments) + 1}",
        patient_id=seed.patient.id,
        doctor_id=doctor.id,
        location_id=seed.tenant.primary_location.id,
        type=AppointmentType.CONSULT,
        scheduled_start=datetime(day.year, day.month, day.day, hour, minute),
        duration_minutes=30,
        reason="Control",
        created_by_id=seed.receptionist.id,
        status=status,
    )
    seed.factory.store.appointments[a.id.value] = a
    return a


def _summary(seed, actor):
    return GetDashboardSummary(seed.factory.for_tenant(seed.tenant.id), CLOCK).execute(actor)


def test_appointments_compare_with_same_weekday_last_week():
    seed = seed_clinic()
    for h in (9, 10, 11):
        _appt(seed, seed.doctor, MONDAY, h)
    _appt(seed, seed.doctor, MONDAY, 12, status=AppointmentStatus.CANCELLED)  # not counted
    _appt(seed, seed.doctor, MONDAY, 12, 30, status=AppointmentStatus.COMPLETED)
    for h in (9, 10):
        _appt(seed, seed.doctor, LAST_MONDAY, h)

    s = _summary(seed, seed.actor(seed.admin))

    assert s.day == MONDAY
    assert s.appointments_today == 4
    assert s.appointments_delta_pct == 100  # 4 vs 2
    assert s.pending_today == 3  # the completed one is no longer pending


def test_no_baseline_means_no_delta():
    seed = seed_clinic()
    _appt(seed, seed.doctor, MONDAY, 9)

    s = _summary(seed, seed.actor(seed.admin))

    assert s.appointments_today == 1
    assert s.appointments_delta_pct is None


def test_occupancy_is_booked_share_of_bookable_slots_with_points_delta():
    seed = seed_clinic()
    for h, m in ((9, 0), (9, 30)):
        _appt(seed, seed.doctor, MONDAY, h, m)
    _appt(seed, seed.doctor, MONDAY, 10, status=AppointmentStatus.NO_SHOW)  # still took it
    _appt(seed, seed.doctor, MONDAY, 11, status=AppointmentStatus.CANCELLED)  # freed it
    _appt(seed, seed.doctor, LAST_MONDAY, 9)

    s = _summary(seed, seed.actor(seed.admin))

    assert s.occupancy_pct == 38  # 3 of 8 slots
    assert s.occupancy_delta_pts == 38 - 12  # last Monday: 1 of 8 → 12%


def test_occupancy_is_none_on_a_day_without_working_hours():
    seed = seed_clinic()
    sunday = FixedClock(datetime(2026, 6, 7, 8, 0))

    s = GetDashboardSummary(seed.factory.for_tenant(seed.tenant.id), sunday).execute(
        seed.actor(seed.admin)
    )

    assert s.occupancy_pct is None
    assert s.occupancy_delta_pts is None


def test_doctor_sees_only_their_own_agenda():
    seed = seed_clinic()
    other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@x.test")
    seed.factory.store.users[other.id.value] = other
    av = build_weekday_availability(seed.tenant.id, other.id)
    seed.factory.store.availability[av.id.value] = av
    _appt(seed, seed.doctor, MONDAY, 9)
    for h in (9, 10, 11, 12):
        _appt(seed, other, MONDAY, h)

    mine = _summary(seed, seed.doctor_actor)
    clinic = _summary(seed, seed.actor(seed.admin))

    assert (mine.appointments_today, mine.occupancy_pct) == (1, 12)  # 1 of 8
    assert (clinic.appointments_today, clinic.occupancy_pct) == (5, 31)  # 5 of 16


def test_patient_growth_over_the_last_week():
    seed = seed_clinic()
    now = CLOCK.now().replace(tzinfo=UTC)
    seed.patient.created_at = now - timedelta(days=30)
    for i, days_ago in enumerate((40, 20, 3, 1)):
        created = now - timedelta(days=days_ago)
        p = build_patient(seed.tenant.id, code=f"P-0020{i}", created_at=created)
        seed.factory.store.patients[p.id.value] = p

    s = _summary(seed, seed.actor(seed.admin))

    assert s.patients_total == 5
    assert s.patients_delta_pct == 67  # 2 new on top of 3 → +67%


def test_missing_permission_hides_the_metric_instead_of_failing():
    seed = seed_clinic()
    actor = replace(seed.actor(seed.admin), permissions=frozenset({"patients.view"}))

    s = _summary(seed, actor)

    assert s.appointments_today is None
    assert s.occupancy_pct is None
    assert s.pending_today is None
    assert s.patients_total == 1
