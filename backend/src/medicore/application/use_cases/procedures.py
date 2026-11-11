"""Minor procedures: the clinic's catalog, the procedures themselves (checklist, consent on
paper, note, signature, amendments) and the worklist.

Procedures ordered in a consultation are born when it is signed (see ``SignConsultation``);
the others are registered here, optionally linked to a procedure appointment. Who may
perform each one comes from the catalog: a doctor always, a nurse only for the types open
to nursing. No files are uploaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.notifications import PROCEDURE_PERFORMED, notify
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.common.timezone import clinic_instant, clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.procedure import (
    Procedure,
    ProcedureProgress,
    ProcedureType,
    can_perform,
)
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    PatientStatus,
    ProcedurePerformer,
    ProcedureSource,
    ProcedureStatus,
    Role,
)
from medicore.domain.services.allergies import allergy_conflicts
from medicore.domain.services.procedure_catalog import DEFAULT_PROCEDURES
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import (
    AppointmentId,
    PatientId,
    ProcedureId,
    ProcedureTypeId,
)
from medicore.domain.value_objects.fee import Charge
from medicore.domain.value_objects.money import Money

# The "Realizados" tab shows what was signed in this many days.
DONE_DAYS = 30
_OPEN_APPOINTMENT = (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED,
                     AppointmentStatus.IN_PROGRESS)


def _patient(uow: UnitOfWork, patient_id: PatientId) -> Patient:
    patient = uow.patients.get_by_id(patient_id)
    if patient is None:
        raise EntityNotFound("Patient", patient_id)
    return patient


def _type(uow: UnitOfWork, type_id: ProcedureTypeId) -> ProcedureType:
    kind = uow.procedures.get_type(type_id)
    if kind is None:
        raise EntityNotFound("ProcedureType", type_id)
    return kind


def _procedure(uow: UnitOfWork, procedure_id: ProcedureId) -> Procedure:
    procedure = uow.procedures.get(procedure_id)
    if procedure is None:
        raise EntityNotFound("Procedure", procedure_id)
    return procedure


def _ensure_performer(actor: ActorContext, performer: ProcedurePerformer) -> None:
    ensure_permission(actor, Permission.PROCEDURES_PERFORM)
    if not can_perform(performer, actor.role):
        raise PermissionDenied("only a doctor may perform this procedure",
                               code="procedure.doctor_only")


def _clash(procedure: Procedure, patient: Patient) -> list[str]:
    return allergy_conflicts(procedure.anesthesia, patient.allergies) if procedure.anesthesia \
        else []


def _label(patient: Patient | None) -> str | None:
    return subject(patient.code, patient.full_name) if patient else None


# ── catalog ───────────────────────────────────────────────────────────────────────────────
def ensure_catalog(uow: UnitOfWork, actor: ActorContext, now: datetime) -> list[ProcedureType]:
    """The clinic's catalog; a clinic that never had one starts with the common procedures.
    Must run inside the caller's ``with uow`` block (it commits nothing itself)."""
    types = uow.procedures.list_types()
    if types:
        return types
    for d in DEFAULT_PROCEDURES:
        uow.procedures.save_type(ProcedureType(
            id=ProcedureTypeId.new(), tenant_id=actor.tenant_id, name=d.name,
            performer=d.performer, requires_consent=d.requires_consent,
            follow_up_days=d.follow_up_days, takes_specimen=d.takes_specimen,
            technique_template=d.technique, instructions_template=d.instructions,
            created_at=now,
        ))
    return uow.procedures.list_types()


class GetProcedureCatalog:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext) -> list[ProcedureType]:
        ensure_permission(actor, Permission.PROCEDURES_VIEW)
        with self._uow:
            types = ensure_catalog(self._uow, actor, self._clock.now())
            self._uow.commit()
        return types


@dataclass(frozen=True, slots=True)
class ProcedureTypeCommand:
    name: str
    performer: ProcedurePerformer
    requires_consent: bool = False
    follow_up_days: int | None = None
    takes_specimen: bool = False
    technique_template: str | None = None
    instructions_template: str | None = None
    price: Money | None = None


def _unique_name(uow: UnitOfWork, name: str, exclude: ProcedureTypeId | None = None) -> None:
    folded = " ".join(name.split()).casefold()
    for t in uow.procedures.list_types():
        if t.id != exclude and t.name.casefold() == folded:
            raise ValidationError("a procedure with that name exists",
                                  code="procedure.name_taken", name=t.name)


class CreateProcedureType:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: ProcedureTypeCommand) -> ProcedureType:
        ensure_permission(actor, Permission.PROCEDURES_CATALOG)
        with self._uow:
            now = self._clock.now()
            ensure_catalog(self._uow, actor, now)
            _unique_name(self._uow, cmd.name)
            kind = ProcedureType(
                id=ProcedureTypeId.new(), tenant_id=actor.tenant_id, name=cmd.name,
                performer=cmd.performer, requires_consent=cmd.requires_consent,
                follow_up_days=cmd.follow_up_days, takes_specimen=cmd.takes_specimen,
                technique_template=cmd.technique_template,
                instructions_template=cmd.instructions_template, created_at=now,
                price=cmd.price,
            )
            self._uow.procedures.save_type(kind)
            self._uow.audit.append(audit_entry(
                actor, now, "procedure.type_created", "ProcedureType", str(kind.id),
                subject=kind.name,
            ))
            self._uow.commit()
        return kind


class UpdateProcedureType:
    """Edit a catalog entry. Procedures already ordered keep the rules they were ordered
    with; the change applies to new ones."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, type_id: ProcedureTypeId,
                cmd: ProcedureTypeCommand) -> ProcedureType:
        ensure_permission(actor, Permission.PROCEDURES_CATALOG)
        with self._uow:
            old = _type(self._uow, type_id)
            _unique_name(self._uow, cmd.name, exclude=type_id)
            kind = ProcedureType(
                id=old.id, tenant_id=old.tenant_id, name=cmd.name, performer=cmd.performer,
                requires_consent=cmd.requires_consent, follow_up_days=cmd.follow_up_days,
                takes_specimen=cmd.takes_specimen, technique_template=cmd.technique_template,
                instructions_template=cmd.instructions_template, active=old.active,
                created_at=old.created_at, price=cmd.price,
            )
            self._uow.procedures.save_type(kind)
            self._uow.audit.append(audit_entry(
                actor, self._clock.now(), "procedure.type_updated", "ProcedureType",
                str(kind.id), subject=kind.name,
            ))
            self._uow.commit()
        return kind


class SetProcedureTypeActive:
    """Archive a type (no new orders; history intact) or bring it back."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, type_id: ProcedureTypeId,
                active: bool) -> ProcedureType:
        ensure_permission(actor, Permission.PROCEDURES_CATALOG)
        with self._uow:
            kind = _type(self._uow, type_id)
            kind.active = active
            self._uow.procedures.save_type(kind)
            self._uow.audit.append(audit_entry(
                actor, self._clock.now(),
                "procedure.type_restored" if active else "procedure.type_archived",
                "ProcedureType", str(kind.id), subject=kind.name,
            ))
            self._uow.commit()
        return kind


# ── procedures ────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class CreateProcedureCommand:
    patient_id: PatientId
    type_id: ProcedureTypeId
    indication: str
    appointment_id: AppointmentId | None = None


class CreateProcedure:
    """Register a procedure directly: a walk-in, or a procedure appointment of the day."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: CreateProcedureCommand) -> Procedure:
        with self._uow:
            kind = _type(self._uow, cmd.type_id)
            _ensure_performer(actor, kind.performer)
            if not kind.active:
                raise ValidationError("the procedure type is archived",
                                      code="procedure.type_inactive")
            patient = _patient(self._uow, cmd.patient_id)
            if patient.status != PatientStatus.ACTIVE:
                raise ValidationError("patient is inactive", code="procedure.patient_inactive")
            if cmd.appointment_id is not None:
                self._check_appointment(cmd.appointment_id, patient)
            now = self._clock.now()
            procedure = Procedure(
                id=ProcedureId.new(), tenant_id=actor.tenant_id, patient_id=patient.id,
                type_id=kind.id, type_name=kind.name, performer=kind.performer,
                requires_consent=kind.requires_consent, source=ProcedureSource.DIRECT,
                indication=cmd.indication, ordered_by_id=actor.user_id,
                created_by_id=actor.user_id, follow_up_days=kind.follow_up_days,
                takes_specimen=kind.takes_specimen, appointment_id=cmd.appointment_id,
                created_at=now, charge=Charge.at_list_price(kind.price),
            )
            self._uow.procedures.save(procedure)
            self._uow.audit.append(audit_entry(
                actor, now, "procedure.created", "Procedure", str(procedure.id),
                subject=_label(patient), procedure=procedure.type_name,
                appointment_id=str(cmd.appointment_id) if cmd.appointment_id else None,
            ))
            self._uow.commit()
        return procedure

    def _check_appointment(self, appointment_id: AppointmentId, patient: Patient) -> None:
        appt = self._uow.appointments.get_by_id(appointment_id)
        if (appt is None or appt.patient_id != patient.id
                or appt.type != AppointmentType.PROCEDURE or appt.status not in _OPEN_APPOINTMENT):
            raise ValidationError("not an open procedure appointment of this patient",
                                  code="procedure.appointment_mismatch")
        taken = [p for p in self._uow.procedures.list_by_appointments([appointment_id])
                 if p.status != ProcedureStatus.CANCELLED]
        if taken:
            raise ValidationError("the appointment already has its procedure",
                                  code="procedure.appointment_taken")


class _Editor:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _load(self, actor: ActorContext, procedure_id: ProcedureId) -> Procedure:
        procedure = _procedure(self._uow, procedure_id)
        _ensure_performer(actor, procedure.performer)
        return procedure


class SaveProcedureProgress(_Editor):
    """Save the checklist, vitals and the note while the procedure is open (no audit: it is
    a draft until signed)."""

    def execute(self, actor: ActorContext, procedure_id: ProcedureId,
                progress: ProcedureProgress) -> Procedure:
        with self._uow:
            procedure = self._load(actor, procedure_id)
            procedure.save_progress(progress, self._clock.now())
            self._uow.procedures.save(procedure)
            self._uow.commit()
        return procedure


class RecordProcedureConsent(_Editor):
    def execute(self, actor: ActorContext, procedure_id: ProcedureId, signer: str,
                relationship: str | None, witness: str) -> Procedure:
        with self._uow:
            procedure = self._load(actor, procedure_id)
            now = self._clock.now()
            procedure.record_consent(signer, relationship, witness, actor.user_id, now)
            self._uow.procedures.save(procedure)
            patient = self._uow.patients.get_by_id(procedure.patient_id)
            self._uow.audit.append(audit_entry(
                actor, now, "procedure.consent_recorded", "Procedure", str(procedure.id),
                subject=_label(patient), procedure=procedure.type_name,
                signer=procedure.consent_signer, relationship=procedure.consent_relationship,
                witness=procedure.consent_witness,
            ))
            self._uow.commit()
        return procedure


class SignProcedure(_Editor):
    """Sign the note: it becomes immutable, the follow-up date is suggested, a linked
    procedure appointment is completed and the ordering doctor is told if someone else
    did it."""

    def execute(self, actor: ActorContext, procedure_id: ProcedureId) -> Procedure:
        with self._uow:
            procedure = self._load(actor, procedure_id)
            patient = _patient(self._uow, procedure.patient_id)
            now = self._clock.now()
            today = clinic_now(self._uow, actor.tenant_id, self._clock).date()
            clashes = _clash(procedure, patient)
            procedure.sign(actor.user_id, now, today, bool(clashes))
            self._uow.procedures.save(procedure)
            if procedure.appointment_id is not None:
                self._complete(procedure.appointment_id)
            notify(
                self._uow, actor, now, PROCEDURE_PERFORMED, [procedure.ordered_by_id],
                patient_id=str(patient.id), patient_name=patient.full_name,
                procedure_id=str(procedure.id),
            )
            self._uow.audit.append(audit_entry(
                actor, now, "procedure.signed", "Procedure", str(procedure.id),
                subject=_label(patient), procedure=procedure.type_name,
                specimen=procedure.specimen_sent or None,
                allergy_override=procedure.allergy_override,
                follow_up_on=procedure.follow_up_on.isoformat()
                if procedure.follow_up_on else None,
            ))
            self._uow.commit()
        return procedure

    def _complete(self, appointment_id: AppointmentId) -> None:
        appt: Appointment | None = self._uow.appointments.get_by_id(appointment_id)
        if appt is None:
            return
        if appt.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED):
            appt.start()
        # A consultation running on the same appointment completes it when it is signed.
        if (appt.status == AppointmentStatus.IN_PROGRESS
                and self._uow.consultations.get_by_appointment(appt.id) is None):
            appt.complete()
        self._uow.appointments.save(appt)


class CancelProcedure(_Editor):
    def execute(self, actor: ActorContext, procedure_id: ProcedureId, reason: str) -> Procedure:
        with self._uow:
            procedure = self._load(actor, procedure_id)
            now = self._clock.now()
            procedure.cancel(actor.user_id, reason, now)
            self._uow.procedures.save(procedure)
            patient = self._uow.patients.get_by_id(procedure.patient_id)
            self._uow.audit.append(audit_entry(
                actor, now, "procedure.cancelled", "Procedure", str(procedure.id),
                subject=_label(patient), procedure=procedure.type_name,
                reason=procedure.cancel_reason,
            ))
            self._uow.commit()
        return procedure


class AmendProcedure:
    """Append a correction to a signed note: by whoever performed it, or any doctor."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, procedure_id: ProcedureId, text: str,
                reason: str) -> Procedure:
        ensure_permission(actor, Permission.PROCEDURES_PERFORM)
        with self._uow:
            procedure = _procedure(self._uow, procedure_id)
            if actor.role != Role.DOCTOR and actor.user_id != procedure.performed_by_id:
                raise PermissionDenied("only the performer or a doctor may amend it",
                                       code="procedure.not_performer")
            now = self._clock.now()
            procedure.amend(actor.user_id, text, reason, now)
            self._uow.procedures.save(procedure)
            patient = self._uow.patients.get_by_id(procedure.patient_id)
            self._uow.audit.append(audit_entry(
                actor, now, "procedure.amended", "Procedure", str(procedure.id),
                subject=_label(patient), procedure=procedure.type_name, reason=reason.strip(),
            ))
            self._uow.commit()
        return procedure


# ── reads ─────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ProcedureView:
    procedure: Procedure
    patient: Patient
    kind: ProcedureType | None  # for the note templates
    allergy_conflicts: list[str]  # the anesthesia against the patient's allergies


class GetProcedure:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, procedure_id: ProcedureId) -> ProcedureView:
        ensure_permission(actor, Permission.PROCEDURES_VIEW)
        procedure = _procedure(self._uow, procedure_id)
        patient = _patient(self._uow, procedure.patient_id)
        return ProcedureView(procedure, patient, self._uow.procedures.get_type(procedure.type_id),
                             _clash(procedure, patient))


class GetPatientProcedures:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[Procedure]:
        ensure_permission(actor, Permission.PROCEDURES_VIEW)
        _patient(self._uow, patient_id)
        return self._uow.procedures.list_by_patient(patient_id)


@dataclass(frozen=True, slots=True)
class ProcedureItem:
    patient: Patient
    procedure: Procedure


@dataclass(frozen=True, slots=True)
class AppointmentItem:
    appointment: Appointment
    patient: Patient
    procedure: Procedure | None  # the one registered for it, if any


@dataclass(frozen=True, slots=True)
class ProcedureWorklist:
    now: datetime  # clinic wall-clock
    pending: list[ProcedureItem]  # open, oldest first
    today: list[AppointmentItem]  # today's procedure appointments, by time
    done: list[ProcedureItem]  # signed in the last DONE_DAYS days, newest first


class GetProcedureWorklist:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext) -> ProcedureWorklist:
        ensure_permission(actor, Permission.PROCEDURES_VIEW)
        uow = self._uow
        now = clinic_now(uow, actor.tenant_id, self._clock)
        patients: dict[PatientId, Patient | None] = {}

        def patient(pid: PatientId) -> Patient | None:
            if pid not in patients:
                patients[pid] = uow.patients.get_by_id(pid)
            return patients[pid]

        def items(procedures: list[Procedure]) -> list[ProcedureItem]:
            return [ProcedureItem(p, x) for x in procedures
                    if (p := patient(x.patient_id)) is not None]

        appointments = sorted(
            (a for a in uow.appointments.list_by_day(now.date())
             if a.type == AppointmentType.PROCEDURE
             and a.status not in (AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW)),
            key=lambda a: a.scheduled_start,
        )
        linked = {
            x.appointment_id: x
            for x in uow.procedures.list_by_appointments([a.id for a in appointments])
            if x.status != ProcedureStatus.CANCELLED
        }
        today = [AppointmentItem(a, p, linked.get(a.id)) for a in appointments
                 if (p := patient(a.patient_id)) is not None]

        tomorrow = datetime.combine(now.date() + timedelta(days=1), time())
        start = clinic_instant(uow, actor.tenant_id, self._clock,
                               tomorrow - timedelta(days=DONE_DAYS))
        end = clinic_instant(uow, actor.tenant_id, self._clock, tomorrow)
        return ProcedureWorklist(
            now=now,
            pending=items(uow.procedures.list_open()),
            today=today,
            done=items(uow.procedures.list_completed_between(start, end)),
        )
