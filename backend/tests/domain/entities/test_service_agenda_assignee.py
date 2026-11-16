"""Who attends an appointment: one doctor or one service agenda, and what an agenda takes."""

from __future__ import annotations

from datetime import datetime

import pytest

from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.fee_schedule import PRICED_TYPES, FeeSchedule
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.enums import AddonModule, AppointmentType, ServiceAgendaKind
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    AppointmentId,
    AvailabilityId,
    FeeScheduleId,
    LocationId,
    PatientId,
    ServiceAgendaId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.assignee import Assignee
from medicore.domain.value_objects.fee import fee

TENANT = TenantId.new()
START = datetime(2026, 6, 1, 9, 0)


def _agenda(name: str = "Vacunatorio") -> ServiceAgenda:
    return ServiceAgenda(
        id=ServiceAgendaId.new(), tenant_id=TENANT, name=name, kind=ServiceAgendaKind.VACCINATION
    )


def _appointment(doctor_id, agenda_id, kind=AppointmentType.VACCINATION) -> Appointment:
    return Appointment(
        id=AppointmentId.new(), tenant_id=TENANT, code="A-1", patient_id=PatientId.new(),
        doctor_id=doctor_id, agenda_id=agenda_id, location_id=LocationId.new(), type=kind,
        scheduled_start=START, duration_minutes=15, reason="Vacuna", created_by_id=UserId.new(),
    )


class TestAssignee:
    def test_a_doctor_or_an_agenda_is_valid(self):
        doctor, agenda = UserId.new(), ServiceAgendaId.new()

        assert Assignee.doctor(doctor).is_doctor
        assert Assignee.doctor(doctor).owner == doctor
        assert not Assignee.agenda(agenda).is_doctor
        assert Assignee.agenda(agenda).owner == agenda

    @pytest.mark.parametrize("doctor,agenda", [(True, True), (False, False)])
    def test_both_or_neither_is_refused(self, doctor, agenda):
        with pytest.raises(DomainError) as error:
            Assignee(UserId.new() if doctor else None, ServiceAgendaId.new() if agenda else None)

        assert error.value.code == "appointment.assignee_required"


class TestAppointmentAssignee:
    def test_an_agenda_appointment_has_no_doctor(self):
        agenda_id = ServiceAgendaId.new()

        appointment = _appointment(None, agenda_id)

        assert appointment.assignee == Assignee.agenda(agenda_id)

    def test_it_needs_exactly_one_assignee(self):
        with pytest.raises(DomainError):
            _appointment(None, None)
        with pytest.raises(DomainError):
            _appointment(UserId.new(), ServiceAgendaId.new())

    def test_a_walk_in_can_go_to_an_agenda(self):
        agenda_id = ServiceAgendaId.new()

        walk_in = Appointment.walk_in(
            id=AppointmentId.new(), tenant_id=TENANT, code="A-2", patient_id=PatientId.new(),
            doctor_id=None, agenda_id=agenda_id, location_id=LocationId.new(),
            type=AppointmentType.VACCINATION, reason="Vacuna", duration_minutes=15,
            created_by_id=UserId.new(), now=START,
        )

        assert walk_in.agenda_id == agenda_id and walk_in.is_walk_in


class TestServiceAgenda:
    def test_vaccination_agenda_takes_only_vaccination_appointments(self):
        agenda = _agenda()

        assert agenda.accepts(AppointmentType.VACCINATION)
        assert not agenda.accepts(AppointmentType.CONSULT)
        with pytest.raises(DomainError) as error:
            agenda.ensure_accepts(AppointmentType.CONSULT)
        assert error.value.code == "appointment.type_not_for_agenda"

    def test_it_needs_the_vaccination_module(self):
        assert _agenda().module == AddonModule.VACCINATION

    def test_the_name_is_tidied_and_required(self):
        assert _agenda("  Sala   de  vacunas ").name == "Sala de vacunas"
        with pytest.raises(InvalidValueObject):
            _agenda("   ")
        with pytest.raises(InvalidValueObject) as error:
            _agenda("x" * 81)
        assert error.value.code == "service_agenda.name_too_long"

    def test_rename_validates_too(self):
        agenda = _agenda()

        agenda.rename("Sala 2", START)

        assert agenda.name == "Sala 2" and agenda.updated_at == START
        with pytest.raises(InvalidValueObject):
            agenda.rename("", START)


class TestAvailabilityAssignee:
    def test_a_schedule_belongs_to_a_doctor_or_an_agenda(self):
        agenda_id = ServiceAgendaId.new()

        availability = DoctorAvailability(
            id=AvailabilityId.new(), tenant_id=TENANT, doctor_id=None, agenda_id=agenda_id
        )

        assert availability.assignee == Assignee.agenda(agenda_id)
        with pytest.raises(DomainError):
            DoctorAvailability(id=AvailabilityId.new(), tenant_id=TENANT, doctor_id=None)


class TestVaccinationIsNotPricedPerDoctor:
    def test_it_is_left_out_of_the_priced_types(self):
        assert AppointmentType.VACCINATION not in PRICED_TYPES

    def test_a_fee_schedule_refuses_a_vaccination_price(self):
        with pytest.raises(InvalidValueObject) as error:
            FeeSchedule(
                id=FeeScheduleId.new(), tenant_id=TENANT, doctor_id=UserId.new(),
                prices={AppointmentType.VACCINATION: fee("5")},
            )

        assert error.value.code == "fee.procedure_from_catalog"
