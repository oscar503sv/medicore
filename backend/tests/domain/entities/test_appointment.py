"""Tests for the Appointment state machine."""

from __future__ import annotations

from datetime import datetime

import pytest

from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus, AppointmentType
from medicore.domain.shared.errors import DomainError, InvalidStateTransition, InvalidValueObject
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


def make_walk_in() -> Appointment:
    return Appointment.walk_in(
        id=AppointmentId.new(),
        tenant_id=TenantId.new(),
        code="A-2402",
        patient_id=PatientId.new(),
        doctor_id=UserId.new(),
        location_id=LocationId.new(),
        type=AppointmentType.EMERGENCY,
        reason="Dolor torácico",
        duration_minutes=30,
        created_by_id=UserId.new(),
        now=datetime(2026, 6, 1, 22, 13, 45, 999),
    )


class TestWalkIn:
    def test_starts_now_to_the_minute_and_waits_confirmed(self):
        appt = make_walk_in()

        assert appt.is_walk_in
        assert appt.status == AppointmentStatus.CONFIRMED
        assert appt.scheduled_start == datetime(2026, 6, 1, 22, 13)

    def test_regular_appointments_are_not_walk_ins(self):
        assert not make_appointment().is_walk_in

    def test_cannot_be_a_no_show(self):
        appt = make_walk_in()

        with pytest.raises(DomainError) as exc:
            appt.mark_no_show()

        assert exc.value.code == "appointment.walk_in_no_show"
        assert appt.status == AppointmentStatus.CONFIRMED

    def test_cannot_be_rescheduled(self):
        appt = make_walk_in()

        with pytest.raises(DomainError) as exc:
            appt.reschedule(datetime(2026, 6, 2, 9, 0))

        assert exc.value.code == "appointment.walk_in_reschedule"

    def test_can_be_cancelled_and_attended(self):
        cancelled = make_walk_in()
        cancelled.cancel()
        attended = make_walk_in()
        attended.start()

        assert cancelled.status == AppointmentStatus.CANCELLED
        assert attended.status == AppointmentStatus.IN_PROGRESS


class TestPreVitals:
    NOW = datetime(2026, 6, 1, 8, 50)

    def test_merges_only_the_given_fields_and_reports_what_changed(self):
        appt = make_appointment(AppointmentStatus.CONFIRMED)
        assert appt.record_pre_vitals({"heart_rate": 72, "spo2": 98}, self.NOW) == (
            "heart_rate", "spo2",
        )
        assert appt.record_pre_vitals({"heart_rate": 72, "glucose": 90}, self.NOW) == ("glucose",)
        assert appt.pre_vitals.spo2 == 98
        assert appt.pre_vitals_saved_at == self.NOW

    def test_a_null_clears_one_reading(self):
        appt = make_appointment(AppointmentStatus.CONFIRMED)
        appt.record_pre_vitals({"heart_rate": 72}, self.NOW)
        assert appt.record_pre_vitals({"heart_rate": None}, self.NOW) == ("heart_rate",)
        assert appt.pre_vitals.is_empty()

    @pytest.mark.parametrize(
        "status",
        [
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.IN_PROGRESS,
            AppointmentStatus.COMPLETED,
            AppointmentStatus.CANCELLED,
            AppointmentStatus.NO_SHOW,
        ],
    )
    def test_only_a_confirmed_appointment_takes_them(self, status):
        appt = make_appointment(status)
        with pytest.raises(DomainError) as exc:
            appt.record_pre_vitals({"heart_rate": 72}, self.NOW)
        assert exc.value.code == "appointment.vitals_closed"
        assert appt.pre_vitals.is_empty()

    def test_invalid_readings_are_refused(self):
        appt = make_appointment(AppointmentStatus.CONFIRMED)
        with pytest.raises(InvalidValueObject):
            appt.record_pre_vitals({"spo2": 140}, self.NOW)
        with pytest.raises(InvalidValueObject):
            appt.record_pre_vitals({"pulse": 70}, self.NOW)
        assert appt.pre_vitals.is_empty()

    @pytest.mark.parametrize(
        "leave",
        [
            lambda a: a.cancel(),
            lambda a: a.mark_no_show(),
            lambda a: a.reschedule(datetime(2026, 6, 2, 9, 0)),
        ],
        ids=["cancel", "no_show", "reschedule"],
    )
    def test_leaving_the_visit_discards_them(self, leave):
        appt = make_appointment(AppointmentStatus.CONFIRMED)
        appt.record_pre_vitals({"heart_rate": 72}, self.NOW)
        leave(appt)
        assert appt.pre_vitals.is_empty()
        assert appt.pre_vitals_saved_at is None

    def test_taking_them_hands_them_over_and_clears_them(self):
        appt = make_appointment(AppointmentStatus.CONFIRMED)
        appt.record_pre_vitals({"heart_rate": 72}, self.NOW)
        vitals, saved_at = appt.take_pre_vitals()
        assert vitals.heart_rate == 72 and saved_at == self.NOW
        assert appt.pre_vitals.is_empty() and appt.pre_vitals_saved_at is None
