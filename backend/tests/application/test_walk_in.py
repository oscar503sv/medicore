"""Walk-in registration: a patient seen now, without a booked slot."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.notifications import APPOINTMENT_WALK_IN
from medicore.application.use_cases.appointments import (
    CancelAppointment,
    GetBookingOptions,
    ListUpcomingAppointments,
    RegisterWalkIn,
    WalkInCommand,
)
from medicore.application.use_cases.fees import UpdateDoctorFees
from medicore.domain.enums import AddonModule, AppointmentStatus, AppointmentType, Role
from medicore.domain.shared.errors import PermissionDenied, SlotUnavailable
from medicore.domain.value_objects.fee import fee
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import build_patient, seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

SUNDAY_NIGHT = datetime(2026, 5, 31, 23, 47, 31, 123)  # a day off, out of hours, with seconds


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _cmd(seed, **overrides):
    values = {
        "patient_id": seed.patient.id,
        "doctor_id": seed.doctor.id,
        "reason": "Dolor torácico",
    }
    values.update(overrides)
    return WalkInCommand(**values)


def _register(seed, actor=None, clock=None, **overrides):
    use_case = RegisterWalkIn(
        _uow(seed), SequentialCodeGenerator(), clock or FixedClock(SUNDAY_NIGHT)
    )
    return use_case.execute(actor or seed.receptionist_actor, _cmd(seed, **overrides))


class TestRegisterWalkIn:
    def test_starts_now_confirmed_with_the_doctors_duration_and_emergency_type(self):
        seed = seed_clinic()

        appt = _register(seed)

        assert appt.is_walk_in
        assert appt.status == AppointmentStatus.CONFIRMED
        assert appt.type == AppointmentType.EMERGENCY
        assert appt.scheduled_start == datetime(2026, 5, 31, 23, 47)
        assert appt.duration_minutes == seed.availability.rules.slot_minutes
        assert appt.location_id == seed.tenant.primary_location.id
        assert _uow(seed).appointments.get_by_id(appt.id) is not None

    def test_charges_the_doctors_list_price_for_the_type(self):
        seed = seed_clinic()
        UpdateDoctorFees(_uow(seed), FixedClock()).execute(
            seed.doctor_actor, seed.doctor.id, {AppointmentType.EMERGENCY: fee(80)}
        )

        appt = _register(seed)

        assert (appt.charge.listed, appt.charge.charged) == (fee(80), fee(80))

    def test_can_overlap_other_appointments_of_other_patients(self):
        seed = seed_clinic()
        other = _register(seed)
        second_patient = build_patient(seed.tenant.id, code="P-00101")
        seed.factory.store.patients[second_patient.id.value] = second_patient

        second = _register(seed, patient_id=second_patient.id)

        assert second.scheduled_start == other.scheduled_start

    def test_works_for_a_doctor_without_availability_with_the_default_duration(self):
        seed = seed_clinic()
        seed.factory.store.availability.clear()

        appt = _register(seed)

        assert appt.duration_minutes == 30

    def test_same_patient_with_an_active_appointment_with_that_doctor_now_is_a_conflict(self):
        seed = seed_clinic()
        first = _register(seed)

        with pytest.raises(SlotUnavailable) as exc:
            _register(seed)

        assert exc.value.code == "walk_in.duplicate"
        assert exc.value.params["appointment_code"] == first.code

    def test_a_cancelled_visit_does_not_block_a_new_one(self):
        seed = seed_clinic()
        first = _register(seed)
        CancelAppointment(_uow(seed), FixedClock()).execute(seed.receptionist_actor, first.id)

        assert _register(seed).status == AppointmentStatus.CONFIRMED

    def test_inactive_patient_is_rejected(self):
        seed = seed_clinic()
        seed.patient.archive()

        with pytest.raises(ValidationError) as exc:
            _register(seed)

        assert exc.value.code == "walk_in.patient_inactive"

    def test_unknown_patient_is_not_found(self):
        seed = seed_clinic()
        with pytest.raises(EntityNotFound):
            _register(seed, patient_id=build_patient(seed.tenant.id, code="P-09999").id)

    @pytest.mark.parametrize("role", [Role.NURSE, Role.RECEPTIONIST, Role.ADMIN])
    def test_only_an_active_doctor_can_attend(self, role):
        seed = seed_clinic()
        not_a_doctor = {
            Role.NURSE: seed.nurse, Role.RECEPTIONIST: seed.receptionist, Role.ADMIN: seed.admin
        }[role]

        with pytest.raises(ValidationError) as exc:
            _register(seed, doctor_id=not_a_doctor.id)

        assert exc.value.code == "walk_in.invalid_doctor"

    def test_suspended_doctor_is_rejected(self):
        seed = seed_clinic()
        seed.doctor.suspend()

        with pytest.raises(ValidationError) as exc:
            _register(seed)

        assert exc.value.code == "walk_in.invalid_doctor"

    def test_procedure_type_needs_the_module(self):
        seed = seed_clinic()
        seed.tenant.subscription = Subscription(plan_code="clinica", modules=frozenset())

        with pytest.raises(PermissionDenied) as exc:
            _register(seed, type=AppointmentType.PROCEDURE)

        assert exc.value.code == "walk_in.module_required"

    def test_procedure_type_with_the_module_is_allowed(self):
        seed = seed_clinic()
        seed.tenant.subscription = Subscription(
            plan_code="clinica", modules=frozenset({AddonModule.PROCEDURES})
        )

        assert _register(seed, type=AppointmentType.PROCEDURE).type == AppointmentType.PROCEDURE

    def test_audits_and_notifies_the_doctor_but_not_the_author(self):
        seed = seed_clinic()

        appt = _register(seed)

        assert _uow(seed).audit.query(action="appointment.walk_in")
        [n] = _uow(seed).notifications.list_by_user(seed.doctor.id)
        assert n.type == APPOINTMENT_WALK_IN
        assert n.data["appointment_id"] == str(appt.id)
        assert n.data["actor_name"] == seed.receptionist.name

    def test_a_doctor_registering_their_own_walk_in_is_not_notified(self):
        seed = seed_clinic()

        _register(seed, actor=seed.doctor_actor)

        assert _uow(seed).notifications.list_by_user(seed.doctor.id) == []

    def test_stays_on_the_dashboard_while_it_waits(self):
        seed = seed_clinic()
        appt = _register(seed)
        later = FixedClock(SUNDAY_NIGHT + timedelta(minutes=10))

        upcoming = ListUpcomingAppointments(_uow(seed), later).execute(
            seed.actor(seed.admin)
        )

        assert [a.id for a in upcoming] == [appt.id]


class TestWalkInPermission:
    def test_reception_and_doctors_have_it_by_default(self):
        seed = seed_clinic()

        assert _register(seed, actor=seed.receptionist_actor)
        other = seed_clinic()
        assert _register(other, actor=other.doctor_actor)

    def test_nurses_do_not_have_it_by_default(self):
        seed = seed_clinic()

        with pytest.raises(PermissionDenied):
            _register(seed, actor=seed.actor(seed.nurse))

    def test_a_nurse_with_the_permission_can(self):
        seed = seed_clinic()
        nurse = replace(
            seed.actor(seed.nurse), permissions=frozenset({"appointments.walk_in"})
        )

        assert _register(seed, actor=nurse).is_walk_in

    def test_administrators_never_can(self):
        seed = seed_clinic()

        with pytest.raises(PermissionDenied):
            _register(seed, actor=seed.actor(seed.admin))


class TestBookingOptionsForWalkIn:
    def test_a_nurse_with_walk_in_can_read_the_options(self):
        seed = seed_clinic()
        nurse = replace(
            seed.actor(seed.nurse), permissions=frozenset({"appointments.walk_in"})
        )

        options = GetBookingOptions(_uow(seed)).execute(nurse)

        assert [d.user.id for d in options.doctors] == [seed.doctor.id]

    def test_a_nurse_without_either_permission_cannot(self):
        seed = seed_clinic()

        with pytest.raises(PermissionDenied):
            GetBookingOptions(_uow(seed)).execute(seed.actor(seed.nurse))
