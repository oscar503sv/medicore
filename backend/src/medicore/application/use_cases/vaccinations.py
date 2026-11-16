"""Vaccination use cases: the patient's card, recording/voiding doses and the worklist."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import Permission, ensure_permission, has_permission
from medicore.application.common.timezone import clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    InjectionSite,
    PatientStatus,
    Role,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
)
from medicore.domain.repositories._support import Paging, PatientFilter
from medicore.domain.services.immunization import (
    SCHEDULE_BY_KEY,
    VACCINES,
    DoseRecord,
    DoseState,
    dose_states,
)
from medicore.domain.shared.identifiers import AppointmentId, PatientId, VaccinationRecordId

MAX_VISIT_DOSES = 20
OPEN_APPOINTMENT_STATUSES = frozenset({
    AppointmentStatus.SCHEDULED,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.IN_PROGRESS,
})


def _may_see(actor: ActorContext, appointment: Appointment) -> bool:
    """Doctors only work their own appointments (and the agendas' ones)."""
    return (
        actor.role != Role.DOCTOR
        or appointment.doctor_id is None
        or appointment.doctor_id == actor.user_id
    )


def _records_for_status(records: list[VaccinationRecord]) -> list[DoseRecord]:
    return [
        DoseRecord(dose_key=r.dose_key, outcome=r.outcome, on=r.occurred_on)
        for r in records
        if not r.is_voided
    ]


def _today(uow: UnitOfWork, actor: ActorContext, clock: Clock) -> date:
    return clinic_now(uow, actor.tenant_id, clock).date()


@dataclass(frozen=True, slots=True)
class VaccinationCard:
    patient: Patient
    today: date
    states: list[DoseState]
    records: list[VaccinationRecord]  # newest first, voided included (shown struck through)


class GetVaccinationCard:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, patient_id: PatientId) -> VaccinationCard:
        ensure_permission(actor, Permission.VACCINATIONS_VIEW)
        patient = self._uow.patients.get_by_id(patient_id)
        if patient is None:
            raise EntityNotFound("Patient", patient_id)
        today = _today(self._uow, actor, self._clock)
        records = self._uow.vaccinations.list_by_patient(patient_id)
        states = dose_states(patient.date_of_birth, patient.sex, today,
                             _records_for_status(records))
        return VaccinationCard(patient, today, states, records)


@dataclass(frozen=True, slots=True)
class RecordVaccinationCommand:
    patient_id: PatientId
    vaccine_code: str
    outcome: VaccinationOutcome
    occurred_on: date
    source: VaccinationSource
    dose_key: str | None = None
    lot: str | None = None
    route: VaccineRoute | None = None
    site: InjectionSite | None = None
    notes: str | None = None


def _build_record(
    uow: UnitOfWork,
    actor: ActorContext,
    clock: Clock,
    patient: Patient,
    cmd: RecordVaccinationCommand,
    appointment_id: AppointmentId | None = None,
) -> VaccinationRecord:
    """Validate one dose against the patient and the vaccine schedule and build its record.
    Shared by the single-dose entry and the doses given in an appointment."""
    if patient.status != PatientStatus.ACTIVE:
        raise ValidationError("patient is inactive", code="vaccination.patient_inactive")
    vaccine = VACCINES.get(cmd.vaccine_code)
    if vaccine is None:
        raise ValidationError(f"unknown vaccine {cmd.vaccine_code!r}",
                              code="vaccination.unknown_vaccine")
    dose = SCHEDULE_BY_KEY.get(cmd.dose_key) if cmd.dose_key else None
    if cmd.dose_key and (dose is None or dose.vaccine != vaccine.code):
        raise ValidationError(f"dose {cmd.dose_key!r} is not a {vaccine.code} dose",
                              code="vaccination.dose_mismatch")

    today = _today(uow, actor, clock)
    if cmd.occurred_on > today:
        raise ValidationError("date is in the future", code="vaccination.future_date")
    if cmd.occurred_on < patient.date_of_birth:
        raise ValidationError("date is before birth", code="vaccination.before_birth")

    # A one-off dose is given once; periodic doses (yearly flu, Td) repeat.
    if dose and not dose.repeat_months and cmd.outcome == VaccinationOutcome.ADMINISTERED:
        already = any(
            r.dose_key == dose.key
            and not r.is_voided
            and r.outcome == VaccinationOutcome.ADMINISTERED
            for r in uow.vaccinations.list_by_patient(patient.id)
        )
        if already:
            raise ValidationError("dose already recorded",
                                  code="vaccination.dose_already_recorded")

    here_given = (
        cmd.source == VaccinationSource.CLINIC
        and cmd.outcome == VaccinationOutcome.ADMINISTERED
    )
    return VaccinationRecord(
        id=VaccinationRecordId.new(),
        tenant_id=actor.tenant_id,
        patient_id=patient.id,
        vaccine_code=vaccine.code,
        dose_key=dose.key if dose else None,
        outcome=cmd.outcome,
        occurred_on=cmd.occurred_on,
        source=cmd.source,
        recorded_by_id=actor.user_id,
        appointment_id=appointment_id,
        lot=cmd.lot if cmd.outcome == VaccinationOutcome.ADMINISTERED else None,
        # Route/site only describe a dose actually given here.
        route=(cmd.route or vaccine.route) if here_given else None,
        site=cmd.site if here_given else None,
        notes=cmd.notes,
        created_at=clock.now(),
    )


def _audit_recorded(
    uow: UnitOfWork, actor: ActorContext, clock: Clock, patient: Patient,
    record: VaccinationRecord,
) -> None:
    uow.audit.append(
        audit_entry(
            actor, clock.now(), "vaccination.recorded", "VaccinationRecord",
            str(record.id), subject=subject(patient.code, patient.full_name),
            vaccine=record.vaccine_code, dose=record.dose_key, status=str(record.outcome),
            appointment_id=str(record.appointment_id) if record.appointment_id else None,
        )
    )


class RecordVaccination:
    """Record a dose given (here or elsewhere), refused or contraindicated."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: RecordVaccinationCommand) -> VaccinationRecord:
        ensure_permission(actor, Permission.VACCINATIONS_RECORD)
        with self._uow:
            patient = self._uow.patients.get_by_id(cmd.patient_id)
            if patient is None:
                raise EntityNotFound("Patient", cmd.patient_id)
            record = _build_record(self._uow, actor, self._clock, patient, cmd)
            self._uow.vaccinations.save(record)
            _audit_recorded(self._uow, actor, self._clock, patient, record)
            self._uow.commit()
        return record


@dataclass(frozen=True, slots=True)
class VisitDose:
    """One dose of a vaccination visit: the patient, the day and the clinic as the place come
    from the visit itself."""

    vaccine_code: str
    outcome: VaccinationOutcome = VaccinationOutcome.ADMINISTERED
    dose_key: str | None = None
    lot: str | None = None
    route: VaccineRoute | None = None
    site: InjectionSite | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class RecordVaccinationVisitCommand:
    appointment_id: AppointmentId
    patient_id: PatientId
    doses: tuple[VisitDose, ...]


@dataclass(frozen=True, slots=True)
class VaccinationVisit:
    appointment: Appointment
    records: list[VaccinationRecord]


class RecordVaccinationVisit:
    """Record every dose given in a vaccination appointment and close the visit.

    Atomic: either all the doses are saved and the appointment is completed, or nothing is.
    An appointment that already has a consultation (a doctor's own vaccination slot) is not
    completed here: the consultation completes it when it is signed, like a procedure."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, cmd: RecordVaccinationVisitCommand
    ) -> VaccinationVisit:
        ensure_permission(actor, Permission.VACCINATIONS_RECORD)
        if not cmd.doses:
            raise ValidationError("a visit needs at least one dose",
                                  code="vaccination.visit_empty")
        if len(cmd.doses) > MAX_VISIT_DOSES:
            raise ValidationError("too many doses in one visit",
                                  code="vaccination.visit_too_long", max=MAX_VISIT_DOSES)
        with self._uow:
            # The appointment first, so two registrations of the same visit queue here and the
            # second finds it closed.
            appointment = self._uow.appointments.get_for_update(cmd.appointment_id)
            if (
                appointment is None
                or appointment.patient_id != cmd.patient_id
                or appointment.type != AppointmentType.VACCINATION
                or appointment.status not in OPEN_APPOINTMENT_STATUSES
                or not _may_see(actor, appointment)
            ):
                raise ValidationError("not an open vaccination appointment of this patient",
                                      code="vaccination.appointment_mismatch")
            patient = self._uow.patients.get_by_id(appointment.patient_id)
            if patient is None:
                raise EntityNotFound("Patient", appointment.patient_id)

            # The doses are dated today, so only today's visit can be closed (a stale one
            # is rescheduled or cancelled instead).
            today = _today(self._uow, actor, self._clock)
            if appointment.scheduled_start.date() != today:
                raise ValidationError("the appointment is not scheduled for today",
                                      code="vaccination.appointment_not_today")
            records = []
            one_off_given: set[str] = set()
            for dose in cmd.doses:
                self._refuse_repeated_one_off(dose, one_off_given)
                record = _build_record(
                    self._uow, actor, self._clock, patient,
                    RecordVaccinationCommand(
                        patient_id=patient.id, vaccine_code=dose.vaccine_code,
                        outcome=dose.outcome, occurred_on=today,
                        source=VaccinationSource.CLINIC, dose_key=dose.dose_key, lot=dose.lot,
                        route=dose.route, site=dose.site, notes=dose.notes,
                    ),
                    appointment_id=appointment.id,
                )
                self._uow.vaccinations.save(record)
                _audit_recorded(self._uow, actor, self._clock, patient, record)
                records.append(record)

            self._close(actor, appointment, patient)
            self._uow.commit()
        return VaccinationVisit(appointment, records)

    @staticmethod
    def _refuse_repeated_one_off(dose: VisitDose, given: set[str]) -> None:
        """A one-off dose is given once, also within the same visit."""
        scheduled = SCHEDULE_BY_KEY.get(dose.dose_key) if dose.dose_key else None
        if (
            scheduled is None
            or scheduled.repeat_months
            or dose.outcome != VaccinationOutcome.ADMINISTERED
        ):
            return
        if scheduled.key in given:
            raise ValidationError("dose already recorded",
                                  code="vaccination.dose_already_recorded")
        given.add(scheduled.key)

    def _close(self, actor: ActorContext, appointment: Appointment, patient: Patient) -> None:
        if appointment.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED):
            appointment.start()
        if (
            appointment.status == AppointmentStatus.IN_PROGRESS
            and self._uow.consultations.get_by_appointment(appointment.id) is None
        ):
            appointment.complete()
            self._uow.audit.append(audit_entry(
                actor, self._clock.now(), "appointment.completed", "Appointment",
                str(appointment.id), subject=subject(appointment.code, patient.full_name),
            ))
        self._uow.appointments.save(appointment)


class VoidVaccination:
    """Void a wrong entry (it stays in the history, struck through, with the reason)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, record_id: VaccinationRecordId, reason: str
    ) -> VaccinationRecord:
        ensure_permission(actor, Permission.VACCINATIONS_RECORD)
        with self._uow:
            record = self._uow.vaccinations.get_by_id(record_id)
            if record is None:
                raise EntityNotFound("VaccinationRecord", record_id)
            record.void(actor.user_id, reason, self._clock.now())
            self._uow.vaccinations.save(record)
            patient = self._uow.patients.get_by_id(record.patient_id)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "vaccination.voided", "VaccinationRecord",
                    str(record.id),
                    subject=subject(patient.code, patient.full_name) if patient else None,
                    vaccine=record.vaccine_code, reason=record.void_reason,
                )
            )
            self._uow.commit()
        return record


@dataclass(frozen=True, slots=True)
class WorklistItem:
    patient: Patient
    state: DoseState


@dataclass(frozen=True, slots=True)
class VaccinationAppointment:
    appointment: Appointment
    patient: Patient
    attendant_name: str | None  # the doctor, or the service agenda in their place


@dataclass(frozen=True, slots=True)
class VaccinationWorklist:
    today: date
    pending: list[WorklistItem]  # due now or overdue, most overdue first
    upcoming: list[WorklistItem]  # due within the horizon, soonest first
    given_today: list[tuple[Patient, VaccinationRecord]]
    appointments_today: list[VaccinationAppointment]  # vaccination visits still to be given


class GetVaccinationWorklist:
    """What the nursing team has to chase: doses due/overdue and those coming up.

    Computed in memory over the active patients — fine at clinic scale (thousands of
    patients); a materialized "next due" column would be the step up if that changes.
    """

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, horizon_days: int = 30) -> VaccinationWorklist:
        ensure_permission(actor, Permission.VACCINATIONS_VIEW)
        today = _today(self._uow, actor, self._clock)
        patients = self._uow.patients.list(
            PatientFilter(status=str(PatientStatus.ACTIVE)), Paging(limit=100_000)
        ).items
        by_patient: dict[PatientId, list[VaccinationRecord]] = {}
        for r in self._uow.vaccinations.list_active_by_patients([p.id for p in patients]):
            by_patient.setdefault(r.patient_id, []).append(r)

        horizon = today + timedelta(days=horizon_days)
        pending: list[WorklistItem] = []
        upcoming: list[WorklistItem] = []
        for p in patients:
            states = dose_states(p.date_of_birth, p.sex, today,
                                 _records_for_status(by_patient.get(p.id, [])))
            for s in states:
                if s.status in ("due", "overdue"):
                    pending.append(WorklistItem(p, s))
                elif s.due_on and s.status in ("due_soon", "upcoming") and s.due_on <= horizon:
                    upcoming.append(WorklistItem(p, s))
        pending.sort(key=lambda i: (i.state.due_on or today, i.patient.last_name))
        upcoming.sort(key=lambda i: (i.state.due_on or today, i.patient.last_name))

        names = {p.id: p for p in patients}
        given_today = [
            (names[r.patient_id], r)
            for r in self._uow.vaccinations.list_administered_on(today)
            if r.patient_id in names
        ]
        return VaccinationWorklist(
            today, pending, upcoming, given_today, self._appointments_today(actor, today, names)
        )

    def _appointments_today(
        self, actor: ActorContext, today: date, patients: dict[PatientId, Patient]
    ) -> list[VaccinationAppointment]:
        # The visits carry names and times of the agenda: for who sees the agenda.
        if not has_permission(actor, Permission.APPOINTMENTS_VIEW):
            return []
        agendas = {a.id: a.name for a in self._uow.service_agendas.list()}
        items = []
        for a in self._uow.appointments.list_by_day(today):
            patient = patients.get(a.patient_id)
            if (
                a.type != AppointmentType.VACCINATION
                or a.status not in OPEN_APPOINTMENT_STATUSES
                or patient is None
                or not _may_see(actor, a)
            ):
                continue
            doctor = self._uow.users.get_by_id(a.doctor_id) if a.doctor_id else None
            attendant = doctor.name if doctor else agendas.get(a.agenda_id) if a.agenda_id else None
            items.append(VaccinationAppointment(a, patient, attendant))
        return items
