"""Tests for the "next pending appointments" list shown on the dashboard."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from medicore.application.use_cases.appointments import ListUpcomingAppointments
from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType, Role
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import AppointmentId
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock

CLOCK = FixedClock(datetime(2026, 6, 5, 18, 0))  # Friday evening: today's agenda is over


def _appt(seed, doctor, start: datetime, status=AppointmentStatus.SCHEDULED) -> Appointment:
    a = Appointment(
        id=AppointmentId.new(),
        tenant_id=seed.tenant.id,
        code=f"A-{len(seed.factory.store.appointments) + 1}",
        patient_id=seed.patient.id,
        doctor_id=doctor.id,
        location_id=seed.tenant.primary_location.id,
        type=AppointmentType.CONSULT,
        scheduled_start=start,
        duration_minutes=30,
        reason="Control",
        created_by_id=seed.receptionist.id,
        status=status,
    )
    seed.factory.store.appointments[a.id.value] = a
    return a


def _upcoming(seed, actor, limit=6):
    return ListUpcomingAppointments(seed.factory.for_tenant(seed.tenant.id), CLOCK).execute(
        actor, limit
    )


def test_lists_pending_appointments_from_now_across_days_in_order():
    seed = seed_clinic()
    _appt(seed, seed.doctor, datetime(2026, 6, 5, 9, 0), AppointmentStatus.COMPLETED)
    _appt(seed, seed.doctor, datetime(2026, 6, 5, 17, 30))  # already past, never attended
    monday = _appt(seed, seed.doctor, datetime(2026, 6, 8, 9, 0), AppointmentStatus.CONFIRMED)
    tuesday = _appt(seed, seed.doctor, datetime(2026, 6, 9, 10, 0))
    _appt(seed, seed.doctor, datetime(2026, 6, 8, 11, 0), AppointmentStatus.CANCELLED)
    later = _appt(seed, seed.doctor, datetime(2026, 6, 8, 12, 0))

    result = _upcoming(seed, seed.actor(seed.admin))

    assert [a.id for a in result] == [monday.id, later.id, tuesday.id]


def test_limit_caps_the_list():
    seed = seed_clinic()
    for hour in (9, 10, 11, 12):
        _appt(seed, seed.doctor, datetime(2026, 6, 8, hour, 0))

    assert len(_upcoming(seed, seed.actor(seed.admin), limit=2)) == 2


def test_doctor_sees_only_their_own_agenda():
    seed = seed_clinic()
    other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@x.test")
    seed.factory.store.users[other.id.value] = other
    mine = _appt(seed, seed.doctor, datetime(2026, 6, 8, 9, 0))
    theirs = _appt(seed, other, datetime(2026, 6, 8, 9, 0))

    assert [a.id for a in _upcoming(seed, seed.doctor_actor)] == [mine.id]
    assert {a.id for a in _upcoming(seed, seed.actor(seed.admin))} == {mine.id, theirs.id}


def test_requires_appointments_view():
    seed = seed_clinic()
    actor = replace(seed.actor(seed.admin), permissions=frozenset({"patients.view"}))

    with pytest.raises(PermissionDenied):
        _upcoming(seed, actor)
