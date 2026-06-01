"""Tests for appointment booking, slot resolution and status transitions."""

from __future__ import annotations

from datetime import datetime

import pytest

from medicore.application.use_cases.appointments import (
    CancelAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    GetAvailableSlots,
    GetBookingOptions,
)
from medicore.domain.enums import AppointmentStatus, AppointmentType
from medicore.domain.services.slot_resolver import SlotStatus
from medicore.domain.shared.errors import PermissionDenied, SlotUnavailable
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

MONDAY_9AM = datetime(2026, 6, 1, 9, 0)  # within Mon 09:00–13:00 availability


def make_create(seed):
    uow = seed.factory.for_tenant(seed.tenant.id)
    return CreateAppointment(uow, SequentialCodeGenerator(), FixedClock()), uow


def booking_cmd(seed, start=MONDAY_9AM, duration=30):
    return CreateAppointmentCommand(
        patient_id=seed.patient.id,
        doctor_id=seed.doctor.id,
        location_id=seed.tenant.primary_location.id,
        type=AppointmentType.CONSULT,
        scheduled_start=start,
        duration_minutes=duration,
        reason="Control de tensión",
    )


def test_create_appointment_within_availability():
    seed = seed_clinic()
    create, uow = make_create(seed)

    appt = create.execute(seed.receptionist_actor, booking_cmd(seed))

    assert appt.code == "A-2401"
    assert appt.status == AppointmentStatus.SCHEDULED
    assert uow.appointments.get_by_id(appt.id) is not None
    assert uow.audit.query(action="appointment.created")


def test_create_appointment_outside_availability_rejected():
    seed = seed_clinic()
    create, _ = make_create(seed)
    # 14:00 is outside the 09:00–13:00 block
    with pytest.raises(SlotUnavailable):
        create.execute(
            seed.receptionist_actor, booking_cmd(seed, start=datetime(2026, 6, 1, 14, 0))
        )


def test_create_appointment_overlap_rejected():
    seed = seed_clinic()
    create, _ = make_create(seed)
    create.execute(seed.receptionist_actor, booking_cmd(seed, start=MONDAY_9AM))
    # Second booking overlapping the same 09:00–09:30 slot
    with pytest.raises(SlotUnavailable):
        create.execute(
            seed.receptionist_actor, booking_cmd(seed, start=datetime(2026, 6, 1, 9, 15))
        )


def test_available_slots_reflect_existing_appointment():
    seed = seed_clinic()
    create, uow = make_create(seed)
    create.execute(seed.receptionist_actor, booking_cmd(seed, start=MONDAY_9AM))

    slots = GetAvailableSlots(uow, FixedClock()).execute(
        seed.receptionist_actor, seed.doctor.id, MONDAY_9AM.date()
    )

    nine = next(s for s in slots if s.start == MONDAY_9AM)
    nine_thirty = next(s for s in slots if s.start == datetime(2026, 6, 1, 9, 30))
    assert nine.status == SlotStatus.TAKEN
    assert nine_thirty.status == SlotStatus.FREE


def test_doctor_without_availability_cannot_be_booked():
    seed = seed_clinic()
    create, _ = make_create(seed)
    cmd = CreateAppointmentCommand(
        patient_id=seed.patient.id,
        doctor_id=seed.nurse.id,  # nurse has no availability configured
        location_id=seed.tenant.primary_location.id,
        type=AppointmentType.CONSULT,
        scheduled_start=MONDAY_9AM,
        duration_minutes=30,
        reason="x",
    )
    with pytest.raises(SlotUnavailable):
        create.execute(seed.receptionist_actor, cmd)


def test_cancel_appointment():
    seed = seed_clinic()
    create, uow = make_create(seed)
    appt = create.execute(seed.receptionist_actor, booking_cmd(seed))

    cancelled = CancelAppointment(uow, FixedClock()).execute(seed.receptionist_actor, appt.id)
    assert cancelled.status == AppointmentStatus.CANCELLED


def test_cancelled_slot_frees_up():
    seed = seed_clinic()
    create, uow = make_create(seed)
    appt = create.execute(seed.receptionist_actor, booking_cmd(seed, start=MONDAY_9AM))
    CancelAppointment(uow, FixedClock()).execute(seed.receptionist_actor, appt.id)

    # Re-booking the freed slot now succeeds
    again = create.execute(seed.receptionist_actor, booking_cmd(seed, start=MONDAY_9AM))
    assert again.status == AppointmentStatus.SCHEDULED


def test_nurse_cannot_create_appointment():
    seed = seed_clinic()
    create, _ = make_create(seed)
    with pytest.raises(PermissionDenied):
        create.execute(seed.actor(seed.nurse), booking_cmd(seed))


class TestBookingOptions:
    def test_receptionist_sees_doctors_and_locations(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        opts = GetBookingOptions(uow).execute(seed.receptionist_actor)
        assert any(d.id == seed.doctor.id for d in opts.doctors)
        assert len(opts.locations) == 1

    def test_doctor_can_get_booking_options(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        opts = GetBookingOptions(uow).execute(seed.doctor_actor)
        assert len(opts.doctors) >= 1

    def test_nurse_cannot_get_booking_options(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            GetBookingOptions(uow).execute(seed.actor(seed.nurse))
