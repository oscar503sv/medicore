"""A vaccination visit: every dose given in an appointment, recorded and the visit closed
in one transaction."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import ROLE_PERMISSIONS, Permission
from medicore.application.use_cases.appointments import CreateAppointment, CreateAppointmentCommand
from medicore.application.use_cases.service_agendas import (
    CreateServiceAgenda,
    CreateServiceAgendaCommand,
)
from medicore.application.use_cases.vaccinations import (
    GetVaccinationWorklist,
    RecordVaccinationVisit,
    RecordVaccinationVisitCommand,
    VisitDose,
)
from medicore.domain.entities.consultation import Consultation
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    Role,
    ServiceAgendaKind,
    VaccinationOutcome,
    VaccineSupply,
)
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import ConsultationId
from tests.support.builders import build_patient, build_weekday_availability, seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

TODAY = date(2026, 5, 31)  # FixedClock default
MONDAY_9AM = datetime(2026, 6, 1, 9, 0)
TODAY_9AM = datetime(2026, 5, 31, 9, 0)


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _agenda(seed):
    agenda = CreateServiceAgenda(_uow(seed), FixedClock()).execute(
        seed.actor(seed.admin),
        CreateServiceAgendaCommand("Vacunatorio", ServiceAgendaKind.VACCINATION),
    )
    availability = build_weekday_availability(
        seed.tenant.id, None, slot_minutes=15, agenda_id=agenda.id
    )
    seed.factory.store.availability[availability.id.value] = availability
    return agenda


def _appointment(
    seed, agenda=None, kind=AppointmentType.VACCINATION, patient=None, on_today=True
):
    appointment = CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
        seed.receptionist_actor,
        CreateAppointmentCommand(
            patient_id=(patient or seed.patient).id,
            doctor_id=None if agenda else seed.doctor.id,
            agenda_id=agenda.id if agenda else None,
            location_id=seed.tenant.primary_location.id, type=kind,
            scheduled_start=MONDAY_9AM, reason="Vacunas",
        ),
    )
    if on_today:  # booked on a working day; the visit is closed on the day it is held
        appointment.scheduled_start = TODAY_9AM
    return appointment


def _visit(seed, appointment, *doses, actor=None, patient=None):
    return RecordVaccinationVisit(_uow(seed), FixedClock()).execute(
        actor or seed.actor(seed.nurse),
        RecordVaccinationVisitCommand(
            appointment_id=appointment.id, patient_id=(patient or seed.patient).id,
            doses=tuple(doses),
        ),
    )


def _dose(vaccine="TD", lot="L-1", **kw):
    kw.setdefault("supply", VaccineSupply.MINSAL)  # free: no price list needed
    return VisitDose(vaccine_code=vaccine, lot=lot, **kw)


@pytest.fixture
def clinic():
    seed = seed_clinic()
    return seed, _agenda(seed)


class TestRecordVisit:
    def test_records_every_dose_and_completes_the_appointment(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        visit = _visit(seed, appt, _dose("TD"), _dose("INFLU", "L-2"))

        assert [r.vaccine_code for r in visit.records] == ["TD", "INFLU"]
        assert all(r.appointment_id == appt.id and r.occurred_on == TODAY
                   for r in visit.records)
        assert _uow(seed).appointments.get_by_id(appt.id).status == AppointmentStatus.COMPLETED
        assert len(_uow(seed).vaccinations.list_by_appointment(appt.id)) == 2
        assert len(_uow(seed).audit.query(action="vaccination.recorded")) == 2
        assert _uow(seed).audit.query(action="appointment.completed")

    def test_a_refusal_is_recorded_without_a_lot(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        visit = _visit(
            seed, appt, VisitDose("TD", outcome=VaccinationOutcome.REFUSED, notes="No quiso")
        )

        assert visit.records[0].outcome == VaccinationOutcome.REFUSED

    def test_one_bad_dose_records_nothing_and_leaves_the_appointment_open(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        with pytest.raises(ValidationError) as error:
            _visit(seed, appt, _dose("TD"), _dose("NOPE"))

        assert error.value.code == "vaccination.unknown_vaccine"
        assert _uow(seed).vaccinations.list_by_appointment(appt.id) == []
        assert _uow(seed).appointments.get_by_id(appt.id).status == AppointmentStatus.SCHEDULED

    def test_only_the_appointment_of_today_can_be_closed(self, clinic):
        seed, agenda = clinic
        later = _appointment(seed, agenda, on_today=False)

        with pytest.raises(ValidationError) as error:
            _visit(seed, later, _dose())

        assert error.value.code == "vaccination.appointment_not_today"
        assert _uow(seed).vaccinations.list_by_appointment(later.id) == []

    def test_the_same_one_off_dose_twice_in_a_visit_is_refused_and_nothing_is_saved(
        self, clinic
    ):
        seed, agenda = clinic
        baby = build_patient(seed.tenant.id, code="P-00200", date_of_birth=date(2026, 1, 15))
        _uow(seed).patients.save(baby)
        appt = _appointment(seed, agenda, patient=baby)

        with pytest.raises(ValidationError) as error:
            _visit(seed, appt, _dose("HEXA", dose_key="HEXA-1"),
                   _dose("HEXA", "L-2", dose_key="HEXA-1"), patient=baby)

        assert error.value.code == "vaccination.dose_already_recorded"
        assert _uow(seed).vaccinations.list_by_patient(baby.id) == []
        assert _uow(seed).appointments.get_by_id(appt.id).status == AppointmentStatus.SCHEDULED

    def test_a_periodic_dose_may_repeat_in_a_visit(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        visit = _visit(seed, appt, _dose("TD", dose_key="TD-1"), _dose("TD", "L-2"))

        assert len(visit.records) == 2

    def test_the_lot_of_a_dose_given_here_is_required(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        with pytest.raises(Exception) as error:
            _visit(seed, appt, VisitDose("TD"))

        assert error.value.code == "vaccination.lot_required"
        assert _uow(seed).appointments.get_by_id(appt.id).status == AppointmentStatus.SCHEDULED

    def test_a_visit_needs_doses(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        with pytest.raises(ValidationError) as error:
            _visit(seed, appt)

        assert error.value.code == "vaccination.visit_empty"

    def test_a_closed_appointment_takes_no_more_doses(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)
        _visit(seed, appt, _dose())

        with pytest.raises(ValidationError) as error:
            _visit(seed, appt, _dose("INFLU"))

        assert error.value.code == "vaccination.appointment_mismatch"

    def test_the_appointment_must_be_a_vaccination_of_that_patient(self, clinic):
        seed, agenda = clinic
        consult = _appointment(seed, kind=AppointmentType.CONSULT)
        appt = _appointment(seed, agenda)
        other = build_patient(seed.tenant.id, code="P-00555")
        _uow(seed).patients.save(other)

        for bad in (
            lambda: _visit(seed, consult, _dose()),
            lambda: _visit(seed, appt, _dose(), patient=other),
        ):
            with pytest.raises(ValidationError) as error:
                bad()
            assert error.value.code == "vaccination.appointment_mismatch"

    def test_the_appointment_is_locked_before_the_doses(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)
        seed.factory.store.lock_log.clear()

        _visit(seed, appt, _dose())

        assert seed.factory.store.lock_log == [("appointment", appt.id.value)]

    def test_an_appointment_with_a_consultation_is_not_completed_here(self):
        seed = seed_clinic()
        appt = _appointment(seed)
        appt.start()
        seed.factory.store.appointments[appt.id.value] = appt
        consultation = Consultation(
            id=ConsultationId.new(), tenant_id=seed.tenant.id, appointment_id=appt.id,
            patient_id=seed.patient.id, doctor_id=seed.doctor.id, started_at=MONDAY_9AM,
        )
        seed.factory.store.consultations[consultation.id.value] = consultation

        _visit(seed, appt, _dose(), actor=seed.doctor_actor)

        assert _uow(seed).appointments.get_by_id(appt.id).status == AppointmentStatus.IN_PROGRESS
        assert len(_uow(seed).vaccinations.list_by_appointment(appt.id)) == 1

    def test_needs_the_record_permission(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        with pytest.raises(PermissionDenied):
            _visit(seed, appt, _dose(), actor=seed.receptionist_actor)
        with pytest.raises(PermissionDenied):
            _visit(seed, appt, _dose(), actor=seed.actor(seed.admin))

    def test_a_doctor_cannot_close_another_doctors_appointment(self, clinic):
        seed, _ = clinic
        appt = _appointment(seed)  # the seed doctor's own vaccination slot
        other = seed.actor(seed.doctor)
        other = type(other)(user_id=type(other.user_id).new(), tenant_id=other.tenant_id,
                            role=other.role)

        with pytest.raises(ValidationError):
            _visit(seed, appt, _dose(), actor=other)


class TestWorklist:
    def test_lists_today_open_vaccination_appointments_with_who_attends(self, clinic):
        seed, agenda = clinic
        today = datetime(2026, 5, 31, 9, 0)
        appt = _appointment(seed, agenda)
        closed = _appointment(seed, agenda)
        closed.scheduled_start = today.replace(hour=10)
        closed.cancel()
        consult = _appointment(seed, kind=AppointmentType.CONSULT)
        consult.scheduled_start = today

        wl = GetVaccinationWorklist(_uow(seed), FixedClock()).execute(seed.actor(seed.nurse))

        assert [(i.appointment.id, i.attendant_name) for i in wl.appointments_today] == [
            (appt.id, "Vacunatorio")
        ]

    def test_a_doctor_sees_the_agendas_and_their_own_only(self, clinic):
        seed, agenda = clinic
        today = datetime(2026, 5, 31, 9, 0)
        by_agenda = _appointment(seed, agenda)
        own = _appointment(seed)
        for a in (by_agenda, own):
            a.scheduled_start = today
        theirs = _appointment(seed)
        theirs.scheduled_start = today
        theirs.doctor_id = type(seed.doctor.id).new()

        wl = GetVaccinationWorklist(_uow(seed), FixedClock()).execute(seed.doctor_actor)

        assert {i.appointment.id for i in wl.appointments_today} == {by_agenda.id, own.id}


class TestWorklistAudience:
    def test_who_cannot_see_the_agenda_gets_no_visits(self, clinic):
        seed, agenda = clinic
        _appointment(seed, agenda)
        no_agenda = replace(
            seed.actor(seed.nurse),
            permissions=frozenset(
                str(p) for p in ROLE_PERMISSIONS[Role.NURSE] - {Permission.APPOINTMENTS_VIEW}
            ),
        )

        wl = GetVaccinationWorklist(_uow(seed), FixedClock()).execute(no_agenda)

        assert wl.appointments_today == []
        assert GetVaccinationWorklist(_uow(seed), FixedClock()).execute(
            seed.actor(seed.nurse)
        ).appointments_today
