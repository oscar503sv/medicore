"""Service agendas (the vaccination room): management, booking, walk-ins and what they touch."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from medicore.application.common.errors import ConflictError, EntityNotFound, ValidationError
from medicore.application.use_cases.analytics import AnalyticsQuery, GetAnalyticsOverview
from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
    GetAvailableSlots,
    GetBookingOptions,
    ListAppointmentsForDay,
    RegisterWalkIn,
    RescheduleAppointment,
    WalkInCommand,
)
from medicore.application.use_cases.availability import (
    GetMyAvailability,
    UpdateBookingRules,
    UpdateWeeklySchedule,
)
from medicore.application.use_cases.consultations import StartConsultation
from medicore.application.use_cases.fees import AdjustAppointmentFee
from medicore.application.use_cases.reports import GetReport, ReportQuery
from medicore.application.use_cases.service_agendas import (
    CreateServiceAgenda,
    CreateServiceAgendaCommand,
    ListServiceAgendas,
    SetServiceAgendaActive,
    UpdateServiceAgenda,
)
from medicore.domain.entities.availability import BookingRules, WeeklyDay
from medicore.domain.enums import AddonModule, AppointmentType, ServiceAgendaKind
from medicore.domain.shared.errors import DomainError, PermissionDenied, SlotUnavailable
from medicore.domain.shared.identifiers import LocationId, ServiceAgendaId
from medicore.domain.value_objects.assignee import Assignee
from medicore.domain.value_objects.fee import fee
from medicore.domain.value_objects.subscription import Subscription
from medicore.domain.value_objects.time_range import TimeRange
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator

MONDAY_9AM = datetime(2026, 6, 1, 9, 0)
VACCINATION = AppointmentType.VACCINATION


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _create_agenda(seed, name="Vacunatorio"):
    return CreateServiceAgenda(_uow(seed), FixedClock()).execute(
        seed.actor(seed.admin), CreateServiceAgendaCommand(name, ServiceAgendaKind.VACCINATION)
    )


def _open_hours(seed, agenda, slot_minutes=15):
    """Mon–Fri 09:00–13:00, set the way the organization admin does."""
    admin = seed.actor(seed.admin)
    weekly = [WeeklyDay(d, True, [TimeRange(time(9, 0), time(13, 0))]) for d in range(5)]
    UpdateWeeklySchedule(_uow(seed), FixedClock()).execute(admin, weekly, agenda.id)
    UpdateBookingRules(_uow(seed), FixedClock()).execute(
        admin, BookingRules(slot_minutes=slot_minutes), agenda.id
    )


def _book(seed, agenda, start=MONDAY_9AM, kind=VACCINATION, actor=None):
    return CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
        actor or seed.receptionist_actor,
        CreateAppointmentCommand(
            patient_id=seed.patient.id, doctor_id=None, agenda_id=agenda.id,
            location_id=seed.tenant.primary_location.id, type=kind,
            scheduled_start=start, reason="Vacunas",
        ),
    )


@pytest.fixture
def clinic():
    seed = seed_clinic()
    agenda = _create_agenda(seed)
    _open_hours(seed, agenda)
    return seed, agenda


class TestManagement:
    def test_admin_creates_and_lists_agendas(self):
        seed = seed_clinic()

        agenda = _create_agenda(seed)

        listed = ListServiceAgendas(_uow(seed)).execute(seed.actor(seed.admin))
        assert [v.agenda.id for v in listed] == [agenda.id]
        assert listed[0].slot_minutes is None
        assert _uow(seed).audit.query(action="service_agenda.created")

    def test_those_who_book_may_list_but_not_create(self):
        seed = seed_clinic()
        _create_agenda(seed)

        assert ListServiceAgendas(_uow(seed)).execute(seed.receptionist_actor)
        with pytest.raises(PermissionDenied):
            CreateServiceAgenda(_uow(seed), FixedClock()).execute(
                seed.receptionist_actor,
                CreateServiceAgendaCommand("Otra", ServiceAgendaKind.VACCINATION),
            )

    def test_the_name_is_unique_whatever_its_case(self):
        seed = seed_clinic()
        _create_agenda(seed, "Vacunatorio")

        with pytest.raises(ConflictError) as error:
            _create_agenda(seed, "vacunatorio")

        assert error.value.code == "service_agenda.name_taken"

    def test_renaming_to_a_taken_name_conflicts_and_changes_nothing(self):
        seed = seed_clinic()
        _create_agenda(seed, "Vacunatorio")
        other = _create_agenda(seed, "Sala 2")

        with pytest.raises(ConflictError):
            UpdateServiceAgenda(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), other.id, name="VACUNATORIO"
            )

        assert _uow(seed).service_agendas.get_by_id(other.id).name == "Sala 2"

    def test_the_vaccination_module_is_needed_to_create_one(self):
        seed = seed_clinic()
        seed.tenant.subscription = Subscription(plan_code="clinica", modules=frozenset())

        with pytest.raises(PermissionDenied) as error:
            _create_agenda(seed)

        assert error.value.code == "service_agenda.module_required"

    def test_the_location_must_belong_to_the_clinic(self):
        seed = seed_clinic()

        with pytest.raises(ValidationError) as error:
            CreateServiceAgenda(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin),
                CreateServiceAgendaCommand(
                    "Sala", ServiceAgendaKind.VACCINATION, LocationId.new()
                ),
            )

        assert error.value.code == "service_agenda.invalid_location"

    def test_an_agenda_is_archived_and_back(self):
        seed = seed_clinic()
        agenda = _create_agenda(seed)

        SetServiceAgendaActive(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), agenda.id, False
        )

        assert not _uow(seed).service_agendas.get_by_id(agenda.id).active
        assert _uow(seed).audit.query(action="service_agenda.archived")
        with pytest.raises(EntityNotFound):
            UpdateServiceAgenda(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), ServiceAgendaId.new(), name="Nada"
            )


class TestSchedule:
    def test_the_schedule_is_edited_with_organization_permission(self):
        seed = seed_clinic()
        agenda = _create_agenda(seed)

        with pytest.raises(PermissionDenied):
            UpdateBookingRules(_uow(seed), FixedClock()).execute(
                seed.receptionist_actor, BookingRules(slot_minutes=15), agenda.id
            )
        # A doctor edits only their own schedule through the agenda-less path.
        with pytest.raises(PermissionDenied):
            GetMyAvailability(_uow(seed)).execute(seed.doctor_actor, agenda.id)

    def test_the_agenda_schedule_is_kept_apart_from_the_doctors(self, clinic):
        seed, agenda = clinic

        mine = GetMyAvailability(_uow(seed)).execute(seed.doctor_actor)
        theirs = GetMyAvailability(_uow(seed)).execute(seed.actor(seed.admin), agenda.id)

        assert mine.doctor_id == seed.doctor.id and mine.agenda_id is None
        assert theirs.agenda_id == agenda.id and theirs.doctor_id is None
        assert theirs.rules.slot_minutes == 15


class TestBooking:
    def test_an_agenda_appointment_has_no_doctor_no_price_and_its_own_duration(self, clinic):
        seed, agenda = clinic

        appt = _book(seed, agenda)

        assert appt.doctor_id is None and appt.agenda_id == agenda.id
        assert appt.duration_minutes == 15
        assert appt.charge.listed is None and appt.charge.charged is None

    def test_a_doctor_can_also_take_a_vaccination_appointment(self):
        seed = seed_clinic()

        appt = CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
            seed.receptionist_actor,
            CreateAppointmentCommand(
                patient_id=seed.patient.id, doctor_id=seed.doctor.id,
                location_id=seed.tenant.primary_location.id, type=VACCINATION,
                scheduled_start=MONDAY_9AM, reason="Vacuna",
            ),
        )

        assert appt.doctor_id == seed.doctor.id and appt.agenda_id is None

    def test_both_or_neither_assignee_is_refused(self, clinic):
        seed, agenda = clinic
        both = CreateAppointmentCommand(
            patient_id=seed.patient.id, doctor_id=seed.doctor.id, agenda_id=agenda.id,
            location_id=seed.tenant.primary_location.id, type=VACCINATION,
            scheduled_start=MONDAY_9AM, reason="x",
        )
        neither = CreateAppointmentCommand(
            patient_id=seed.patient.id, doctor_id=None,
            location_id=seed.tenant.primary_location.id, type=VACCINATION,
            scheduled_start=MONDAY_9AM, reason="x",
        )

        for cmd in (both, neither):
            with pytest.raises(DomainError) as error:
                CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
                    seed.receptionist_actor, cmd
                )
            assert error.value.code == "appointment.assignee_required"

    def test_an_agenda_only_takes_its_own_type(self, clinic):
        seed, agenda = clinic

        with pytest.raises(DomainError) as error:
            _book(seed, agenda, kind=AppointmentType.CONSULT)

        assert error.value.code == "appointment.type_not_for_agenda"

    def test_an_archived_agenda_takes_no_bookings(self, clinic):
        seed, agenda = clinic
        SetServiceAgendaActive(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), agenda.id, False
        )

        with pytest.raises(ValidationError) as error:
            _book(seed, agenda)

        assert error.value.code == "service_agenda.inactive"

    def test_the_vaccination_module_is_required_for_the_type_and_the_agenda(self, clinic):
        seed, agenda = clinic
        seed.tenant.subscription = Subscription(plan_code="clinica", modules=frozenset())

        with pytest.raises(PermissionDenied) as error:
            _book(seed, agenda)
        assert error.value.code == "appointment.module_required"
        assert error.value.params["module"] == str(AddonModule.VACCINATION)

        with pytest.raises(PermissionDenied):
            CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
                seed.receptionist_actor,
                CreateAppointmentCommand(
                    patient_id=seed.patient.id, doctor_id=seed.doctor.id,
                    location_id=seed.tenant.primary_location.id, type=VACCINATION,
                    scheduled_start=MONDAY_9AM, reason="x",
                ),
            )

    def test_overlap_is_checked_per_agenda_and_not_against_doctors(self, clinic):
        seed, agenda = clinic
        _book(seed, agenda)

        with pytest.raises(SlotUnavailable):
            _book(seed, agenda)

        # The doctor's 09:00 is free: same time, other assignee.
        CreateAppointment(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
            seed.receptionist_actor,
            CreateAppointmentCommand(
                patient_id=seed.patient.id, doctor_id=seed.doctor.id,
                location_id=seed.tenant.primary_location.id, type=AppointmentType.CONSULT,
                scheduled_start=MONDAY_9AM, reason="x",
            ),
        )

    def test_slots_come_from_the_agenda_schedule(self, clinic):
        seed, agenda = clinic
        _book(seed, agenda)

        slots = GetAvailableSlots(_uow(seed), FixedClock()).execute(
            seed.receptionist_actor, Assignee.agenda(agenda.id), MONDAY_9AM.date()
        )

        by_start = {s.start: s.status for s in slots}
        assert str(by_start[MONDAY_9AM]) == "taken"
        assert str(by_start[datetime(2026, 6, 1, 9, 15)]) == "free"

    def test_booking_locks_the_agenda_before_the_counter(self, clinic):
        seed, agenda = clinic
        seed.factory.store.lock_log.clear()

        _book(seed, agenda)

        assert seed.factory.store.lock_log == [("agenda_bookings", agenda.id.value)]

    def test_reschedule_moves_within_the_agenda(self, clinic):
        seed, agenda = clinic
        appt = _book(seed, agenda)
        seed.factory.store.lock_log.clear()

        moved = RescheduleAppointment(_uow(seed), FixedClock()).execute(
            seed.receptionist_actor, appt.id, datetime(2026, 6, 1, 10, 0)
        )

        assert moved.scheduled_start == datetime(2026, 6, 1, 10, 0)
        assert seed.factory.store.lock_log == [
            ("appointment", appt.id.value), ("agenda_bookings", agenda.id.value)
        ]

    def test_booking_options_list_active_agendas_of_contracted_modules(self, clinic):
        seed, agenda = clinic
        _create_agenda(seed, "Archivada")
        archived = [a for a in _uow(seed).service_agendas.list() if a.name == "Archivada"][0]
        SetServiceAgendaActive(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), archived.id, False
        )

        options = GetBookingOptions(_uow(seed)).execute(seed.receptionist_actor)

        assert [(o.agenda.id, o.slot_minutes) for o in options.agendas] == [(agenda.id, 15)]
        seed.tenant.subscription = Subscription(plan_code="clinica", modules=frozenset())
        assert GetBookingOptions(_uow(seed)).execute(seed.receptionist_actor).agendas == []

    def test_a_doctor_does_not_see_the_agenda_appointments_in_their_day(self, clinic):
        seed, agenda = clinic
        _book(seed, agenda)
        day = MONDAY_9AM.date()

        assert ListAppointmentsForDay(_uow(seed)).execute(seed.receptionist_actor, day)
        assert not ListAppointmentsForDay(_uow(seed)).execute(seed.doctor_actor, day)
        assert ListAppointmentsForDay(_uow(seed)).execute(
            seed.receptionist_actor, day, agenda_id=agenda.id
        )


class TestWalkIn:
    def _walk_in(self, seed, agenda, clock=None):
        return RegisterWalkIn(
            _uow(seed), SequentialCodeGenerator(), clock or FixedClock(MONDAY_9AM)
        ).execute(
            seed.receptionist_actor,
            WalkInCommand(
                patient_id=seed.patient.id, doctor_id=None, agenda_id=agenda.id,
                reason="Vacuna", type=VACCINATION,
            ),
        )

    def test_registers_a_confirmed_agenda_visit_with_the_agenda_duration(self, clinic):
        seed, agenda = clinic

        appt = self._walk_in(seed, agenda)

        assert appt.is_walk_in and appt.agenda_id == agenda.id and appt.doctor_id is None
        assert appt.duration_minutes == 15 and str(appt.status) == "confirmed"

    def test_the_same_patient_twice_now_is_a_duplicate(self, clinic):
        seed, agenda = clinic
        self._walk_in(seed, agenda)

        with pytest.raises(SlotUnavailable) as error:
            self._walk_in(seed, agenda)

        assert error.value.code == "walk_in.duplicate"

    def test_the_module_gate_uses_the_walk_in_code(self, clinic):
        seed, agenda = clinic
        seed.tenant.subscription = Subscription(plan_code="clinica", modules=frozenset())

        with pytest.raises(PermissionDenied) as error:
            self._walk_in(seed, agenda)

        assert error.value.code == "walk_in.module_required"


class TestWhatAnAgendaAppointmentIsNot:
    def test_no_consultation_starts_on_it(self, clinic):
        seed, agenda = clinic
        appt = _book(seed, agenda)

        with pytest.raises(DomainError) as error:
            StartConsultation(_uow(seed), FixedClock()).execute(seed.doctor_actor, appt.id)

        assert error.value.code == "consultation.not_for_agenda"

    def test_only_who_manages_every_fee_adjusts_its_charge(self, clinic):
        seed, agenda = clinic
        appt = _book(seed, agenda)

        with pytest.raises(PermissionDenied):
            AdjustAppointmentFee(_uow(seed), FixedClock()).execute(
                seed.doctor_actor, appt.id, fee("0"), None
            )
        # The admin may price it; there is just nothing to discount before any dose.
        with pytest.raises(DomainError) as error:
            AdjustAppointmentFee(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), appt.id, fee("0"), None
            )
        assert error.value.code == "fee.vaccination_pending"

    def test_clinic_metrics_count_it_without_a_doctor_row(self, clinic):
        seed, agenda = clinic
        _book(seed, agenda)

        overview = GetAnalyticsOverview(_uow(seed), FixedClock(MONDAY_9AM)).execute(
            seed.actor(seed.admin),
            AnalyticsQuery(start=date(2026, 6, 1), end=date(2026, 6, 1)),
        )

        assert overview.current.booked == 1
        assert all(d.doctor_id != str(agenda.id) for d in overview.doctors or [])

    def test_reports_name_the_agenda_where_the_doctor_goes(self, clinic):
        seed, agenda = clinic
        _book(seed, agenda)

        report = GetReport(_uow(seed), FixedClock(MONDAY_9AM)).execute(
            seed.actor(seed.admin),
            ReportQuery("appointments", date(2026, 6, 1), date(2026, 6, 1)),
        )

        keys = [c.key for c in report.detail.columns]
        assert [row[keys.index("doctor")] for row in report.detail.rows] == ["Vacunatorio"]
