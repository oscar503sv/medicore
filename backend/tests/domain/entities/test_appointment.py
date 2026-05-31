"""Tests for the Appointment state machine."""

from __future__ import annotations

from datetime import datetime

import pytest

from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType
from medicore.domain.shared.errors import InvalidStateTransition
from medicore.domain.shared.identifiers import (
    AppointmentId,
    LocationId,
    PatientId,
    TenantId,
    UserId,
)


def make_appointment(status: AppointmentStatus = AppointmentStatus.SCHEDULED) -> Appointment:
    appt = Appointment(
        id=AppointmentId.new(),
        tenant_id=TenantId.new(),
        code="A-2401",
        patient_id=PatientId.new(),
        doctor_id=UserId.new(),
        location_id=LocationId.new(),
        type=AppointmentType.CONSULT,
        scheduled_start=datetime(2026, 6, 1, 9, 0),
        duration_minutes=30,
        reason="Checkup",
        created_by_id=UserId.new(),
    )
    appt.status = status
    return appt


class TestAppointmentTransitions:
    def test_happy_path(self):
        appt = make_appointment()
        appt.confirm()
        assert appt.status == AppointmentStatus.CONFIRMED
        appt.start()
        assert appt.status == AppointmentStatus.IN_PROGRESS
        appt.complete()
        assert appt.status == AppointmentStatus.COMPLETED

    def test_scheduled_can_start_directly(self):
        appt = make_appointment()
        appt.start()
        assert appt.status == AppointmentStatus.IN_PROGRESS

    @pytest.mark.parametrize("status", [AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED])
    def test_can_cancel_or_no_show(self, status):
        appt = make_appointment(status)
        appt.cancel()
        assert appt.status == AppointmentStatus.CANCELLED

        appt2 = make_appointment(status)
        appt2.mark_no_show()
        assert appt2.status == AppointmentStatus.NO_SHOW

    def test_cannot_complete_without_starting(self):
        appt = make_appointment()
        with pytest.raises(InvalidStateTransition):
            appt.complete()

    def test_cannot_cancel_completed(self):
        appt = make_appointment(AppointmentStatus.COMPLETED)
        with pytest.raises(InvalidStateTransition):
            appt.cancel()

    def test_cannot_start_cancelled(self):
        appt = make_appointment(AppointmentStatus.CANCELLED)
        with pytest.raises(InvalidStateTransition):
            appt.start()

    def test_scheduled_end_and_active(self):
        appt = make_appointment()
        assert appt.scheduled_end == datetime(2026, 6, 1, 9, 30)
        assert appt.is_active
        appt.cancel()
        assert not appt.is_active

    def test_reschedule_only_before_progress(self):
        appt = make_appointment(AppointmentStatus.IN_PROGRESS)
        with pytest.raises(InvalidStateTransition):
            appt.reschedule(datetime(2026, 6, 2, 10, 0))
