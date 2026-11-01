"""Vaccination use cases: the patient's card, recording/voiding doses and the worklist."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.common.timezone import clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.enums import (
    InjectionSite,
    PatientStatus,
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
from medicore.domain.shared.identifiers import PatientId, VaccinationRecordId


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

            today = _today(self._uow, actor, self._clock)
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
                    for r in self._uow.vaccinations.list_by_patient(patient.id)
                )
                if already:
                    raise ValidationError("dose already recorded",
                                          code="vaccination.dose_already_recorded")

            here_given = (
                cmd.source == VaccinationSource.CLINIC
                and cmd.outcome == VaccinationOutcome.ADMINISTERED
            )
            record = VaccinationRecord(
                id=VaccinationRecordId.new(),
                tenant_id=actor.tenant_id,
                patient_id=patient.id,
                vaccine_code=vaccine.code,
                dose_key=dose.key if dose else None,
                outcome=cmd.outcome,
                occurred_on=cmd.occurred_on,
                source=cmd.source,
                recorded_by_id=actor.user_id,
                lot=cmd.lot if cmd.outcome == VaccinationOutcome.ADMINISTERED else None,
                # Route/site only describe a dose actually given here.
                route=(cmd.route or vaccine.route) if here_given else None,
                site=cmd.site if here_given else None,
                notes=cmd.notes,
                created_at=self._clock.now(),
            )
            self._uow.vaccinations.save(record)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "vaccination.recorded", "VaccinationRecord",
                    str(record.id), subject=subject(patient.code, patient.full_name),
                    vaccine=vaccine.code, dose=record.dose_key, status=str(record.outcome),
                )
            )
            self._uow.commit()
        return record


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
class VaccinationWorklist:
    today: date
    pending: list[WorklistItem]  # due now or overdue, most overdue first
    upcoming: list[WorklistItem]  # due within the horizon, soonest first
    given_today: list[tuple[Patient, VaccinationRecord]]


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
        return VaccinationWorklist(today, pending, upcoming, given_today)
