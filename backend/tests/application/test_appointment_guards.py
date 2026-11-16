"""Who and what an appointment may refer to, and who may act on it."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    MarkNoShow,
    RegisterWalkIn,
    RescheduleAppointment,
    WalkInCommand,
)
from medicore.application.use_cases.consultations import (
    GetAppointmentVitals,
    UpdateAppointmentVitals,
)
from medicore.application.use_cases.fees import AdjustAppointmentFee
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    PatientStatus,
    Role,
    ServiceAgendaKind,
    UserStatus,
)
from medicore.domain.shared.errors import DomainError, PermissionDenied
from medicore.domain.shared.identifiers import (
    InsurerId,
    LocationId,
    ServiceAgendaId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.fee import fee
from tests.support.builders import build_patient, build_user, seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

MONDAY_9AM = datetime(2026, 6, 1, 9, 0)


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _create(seed, **overrides):
    values = {
        "patient_id": seed.patient.id, "doctor_id": seed.doctor.id,
        "location_id": seed.tenant.primary_location.id, "type": AppointmentType.CONSULT,
        "scheduled_start": MONDAY_9AM, "reason": "Control",
    }
    return CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
        seed.receptionist_actor, CreateAppointmentCommand(**(values | overrides))
    )


def _other_clinic_insurer(seed) -> InsurerId:
    foreign = Insurer(id=InsurerId.new(), tenant_id=TenantId.new(), name="Ajeno")
    seed.factory.store.insurers[foreign.id.value] = foreign
    return foreign.id


class TestBookingReferences:
    def test_an_unknown_patient_is_not_found(self):
        seed = seed_clinic()
        stranger = build_patient(TenantId.new(), code="P-9")  # another clinic's patient
        seed.factory.store.patients[stranger.id.value] = stranger

        with pytest.raises(EntityNotFound):
            _create(seed, patient_id=stranger.id)

    def test_an_inactive_patient_cannot_be_booked(self):
        seed = seed_clinic()
        seed.patient.status = PatientStatus.INACTIVE

        with pytest.raises(ValidationError) as error:
            _create(seed)

        assert error.value.code == "appointment.patient_inactive"

    def test_the_location_must_belong_to_the_clinic(self):
        seed = seed_clinic()

        with pytest.raises(ValidationError) as error:
            _create(seed, location_id=LocationId.new())

        assert error.value.code == "appointment.invalid_location"

    def test_the_insurer_must_belong_to_the_clinic(self):
        seed = seed_clinic()

        with pytest.raises(ValidationError) as error:
            _create(seed, insurance_id=_other_clinic_insurer(seed))

        assert error.value.code == "appointment.invalid_insurer"

    def test_nothing_is_saved_when_a_reference_is_refused(self):
        seed = seed_clinic()

        with pytest.raises(ValidationError):
            _create(seed, location_id=LocationId.new())

        assert _uow(seed).appointments.list_by_day(MONDAY_9AM.date()) == []

    def test_the_walk_in_checks_location_and_insurer_too(self):
        seed = seed_clinic()
        walk_in = RegisterWalkIn(_uow(seed), SequentialCodeGenerator(), FixedClock())

        with pytest.raises(ValidationError) as location:
            walk_in.execute(seed.receptionist_actor, WalkInCommand(
                patient_id=seed.patient.id, doctor_id=seed.doctor.id, reason="x",
                location_id=LocationId.new(),
            ))
        with pytest.raises(ValidationError) as insurer:
            walk_in.execute(seed.receptionist_actor, WalkInCommand(
                patient_id=seed.patient.id, doctor_id=seed.doctor.id, reason="x",
                insurance_id=InsurerId(uuid4()),
            ))

        assert location.value.code == "walk_in.invalid_location"
        assert insurer.value.code == "walk_in.invalid_insurer"


class TestWhoAttends:
    def _other_doctor(self, seed, **kw):
        other = build_user(seed.tenant.id, Role.DOCTOR, email="otro@clinica.test", **kw)
        seed.factory.store.users[other.id.value] = other
        return other

    def _book(self, seed, actor, **overrides):
        values = {
            "patient_id": seed.patient.id, "doctor_id": seed.doctor.id,
            "location_id": seed.tenant.primary_location.id, "type": AppointmentType.CONSULT,
            "scheduled_start": MONDAY_9AM, "reason": "Control",
        }
        return CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
            actor, CreateAppointmentCommand(**(values | overrides))
        )

    def _walk_in(self, seed, actor, **overrides):
        values = {"patient_id": seed.patient.id, "doctor_id": seed.doctor.id, "reason": "x"}
        return RegisterWalkIn(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
            actor, WalkInCommand(**(values | overrides))
        )

    def test_a_doctor_cannot_book_for_another_doctor(self):
        seed = seed_clinic()
        other = self._other_doctor(seed)
        seed.factory.store.lock_log.clear()

        with pytest.raises(PermissionDenied) as booking:
            self._book(seed, seed.doctor_actor, doctor_id=other.id)
        with pytest.raises(PermissionDenied) as walk_in:
            self._walk_in(seed, seed.doctor_actor, doctor_id=other.id)

        assert booking.value.code == walk_in.value.code == "appointment.not_own"
        assert seed.factory.store.lock_log == []  # refused before taking any lock

    def test_a_doctor_books_for_themselves_and_for_an_agenda(self):
        seed = seed_clinic()

        assert self._book(seed, seed.doctor_actor).doctor_id == seed.doctor.id
        assert self._walk_in(seed, seed.doctor_actor).doctor_id == seed.doctor.id
        agenda_id = _agenda_id(seed)
        assert self._walk_in(
            seed, seed.doctor_actor, doctor_id=None, agenda_id=agenda_id,
            type=AppointmentType.VACCINATION,
        ).agenda_id == agenda_id

    def test_reception_books_for_any_doctor(self):
        seed = seed_clinic()
        other = self._other_doctor(seed)

        assert self._walk_in(seed, seed.receptionist_actor, doctor_id=other.id)

    @pytest.mark.parametrize("who", ["unknown", "nurse", "suspended"])
    def test_the_doctor_must_be_an_active_doctor(self, who):
        seed = seed_clinic()
        doctor_id = {
            "unknown": UserId.new(),
            "nurse": seed.nurse.id,
            "suspended": self._other_doctor(seed, status=UserStatus.SUSPENDED).id,
        }[who]

        with pytest.raises(ValidationError) as error:
            self._book(seed, seed.receptionist_actor, doctor_id=doctor_id)

        assert error.value.code == "appointment.invalid_doctor"


class TestNoVitalsOnAgendaAppointments:
    def _agenda_appointment(self, seed):
        appt = _create(seed)
        appt.doctor_id, appt.agenda_id = None, _agenda_id(seed)
        appt.status = AppointmentStatus.CONFIRMED
        return appt

    def test_recording_is_refused(self):
        seed = seed_clinic()
        appt = self._agenda_appointment(seed)

        with pytest.raises(DomainError) as error:
            UpdateAppointmentVitals(_uow(seed), FixedClock()).execute(
                seed.actor(seed.nurse), appt.id, {"heart_rate": 70}
            )

        assert error.value.code == "appointment.vitals_closed"

    def test_reading_is_refused(self):
        seed = seed_clinic()
        appt = self._agenda_appointment(seed)

        with pytest.raises(DomainError) as error:
            GetAppointmentVitals(_uow(seed), FixedClock()).execute(
                seed.actor(seed.nurse), appt.id
            )

        assert error.value.code == "appointment.vitals_closed"


_TRANSITIONS = {
    "confirm": lambda seed, actor, appt: ConfirmAppointment(_uow(seed), FixedClock()).execute(
        actor, appt.id),
    "cancel": lambda seed, actor, appt: CancelAppointment(_uow(seed), FixedClock()).execute(
        actor, appt.id),
    "no_show": lambda seed, actor, appt: MarkNoShow(_uow(seed), FixedClock()).execute(
        actor, appt.id),
    "reschedule": lambda seed, actor, appt: RescheduleAppointment(
        _uow(seed), FixedClock()).execute(actor, appt.id, datetime(2026, 6, 1, 10, 0)),
    "adjust_fee": lambda seed, actor, appt: AdjustAppointmentFee(
        _uow(seed), FixedClock()).execute(actor, appt.id, fee("0"), None),
}


class TestDoctorsActOnTheirOwn:
    @pytest.mark.parametrize("action", sorted(_TRANSITIONS))
    def test_a_doctor_cannot_touch_another_doctors_appointment(self, action):
        seed = seed_clinic()
        appt = _create(seed)
        other = build_user(seed.tenant.id, Role.DOCTOR, email="otro@clinica.test")
        seed.factory.store.users[other.id.value] = other

        with pytest.raises(PermissionDenied) as error:
            _TRANSITIONS[action](seed, seed.actor(other), appt)

        assert error.value.code == "appointment.not_own"

    @pytest.mark.parametrize("action", sorted(_TRANSITIONS))
    def test_a_doctor_cannot_touch_an_agenda_appointment(self, action):
        seed = seed_clinic()
        appt = _create(seed)
        appt.doctor_id, appt.agenda_id = None, _agenda_id(seed)

        with pytest.raises(PermissionDenied) as error:
            _TRANSITIONS[action](seed, seed.doctor_actor, appt)

        assert error.value.code == "appointment.not_own"

    @pytest.mark.parametrize("action", ["confirm", "cancel", "no_show", "reschedule"])
    def test_a_doctor_acts_on_their_own(self, action):
        seed = seed_clinic()
        appt = _create(seed)

        _TRANSITIONS[action](seed, seed.doctor_actor, appt)

    @pytest.mark.parametrize("action", ["confirm", "cancel", "no_show"])
    def test_reception_is_not_narrowed(self, action):
        seed = seed_clinic()
        appt = _create(seed)

        _TRANSITIONS[action](seed, seed.receptionist_actor, appt)


def _agenda_id(seed):
    agenda = ServiceAgenda(
        ServiceAgendaId.new(), seed.tenant.id, "Vac", ServiceAgendaKind.VACCINATION
    )
    seed.factory.store.service_agendas[agenda.id.value] = agenda
    return agenda.id
