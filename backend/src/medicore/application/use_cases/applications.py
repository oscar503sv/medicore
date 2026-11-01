"""In-clinic medication applications: orders, recording each dose, observation and the
nursing worklist.

Internal orders are born when a doctor signs a consultation with indicated applications
(see ``SignConsultation``); external ones are registered here by the nursing team from an
outside prescription (doctor's name + JVPM number). No files are uploaded.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.notifications import APPLICATION_REACTION, notify
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.common.timezone import clinic_instant, clinic_now
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.application import (
    DEFAULT_OBSERVATION_MINUTES,
    ApplicationOrder,
    ApplicationOrderClosed,
    ApplicationRecord,
)
from medicore.domain.entities.patient import Patient
from medicore.domain.enums import (
    ApplicationOrderSource,
    ApplicationOutcome,
    ApplicationRoute,
    ApplicationSite,
    PatientStatus,
)
from medicore.domain.services.allergies import allergy_conflicts
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    PatientId,
)

# A dose due more than this long ago (and not recorded) shows as late on the worklist.
LATE_AFTER = timedelta(minutes=60)


def _settled(records: list[ApplicationRecord]) -> set[int]:
    return {r.dose_number for r in records if not r.is_voided}


def _patient(uow: UnitOfWork, patient_id: PatientId) -> Patient:
    patient = uow.patients.get_by_id(patient_id)
    if patient is None:
        raise EntityNotFound("Patient", patient_id)
    return patient


def _order(uow: UnitOfWork, order_id: ApplicationOrderId) -> ApplicationOrder:
    order = uow.applications.get_order(order_id)
    if order is None:
        raise EntityNotFound("ApplicationOrder", order_id)
    return order


def _record(uow: UnitOfWork, record_id: ApplicationRecordId) -> ApplicationRecord:
    record = uow.applications.get_record(record_id)
    if record is None:
        raise EntityNotFound("ApplicationRecord", record_id)
    return record


def _refresh(uow: UnitOfWork, order: ApplicationOrder) -> None:
    order.refresh(_settled(uow.applications.list_records_by_orders([order.id])))
    uow.applications.save_order(order)


# ── external orders ───────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class CreateExternalOrderCommand:
    patient_id: PatientId
    drug: str
    dose: str
    route: ApplicationRoute
    prescriber: str
    jvpm: str
    doses_total: int = 1
    interval_hours: int | None = None
    observation_minutes: int = DEFAULT_OBSERVATION_MINUTES
    instructions: str | None = None


class CreateExternalOrder:
    """Register an outside prescription to be applied here ("aplicación sin cita")."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: CreateExternalOrderCommand) -> ApplicationOrder:
        ensure_permission(actor, Permission.APPLICATIONS_ADMINISTER)
        with self._uow:
            patient = _patient(self._uow, cmd.patient_id)
            if patient.status != PatientStatus.ACTIVE:
                raise ValidationError("patient is inactive", code="application.patient_inactive")
            now = self._clock.now()
            order = ApplicationOrder(
                id=ApplicationOrderId.new(),
                tenant_id=actor.tenant_id,
                patient_id=patient.id,
                drug=cmd.drug,
                dose=cmd.dose,
                route=cmd.route,
                source=ApplicationOrderSource.EXTERNAL,
                starts_at=clinic_now(self._uow, actor.tenant_id, self._clock).replace(
                    second=0, microsecond=0
                ),
                created_by_id=actor.user_id,
                doses_total=cmd.doses_total,
                interval_hours=cmd.interval_hours,
                observation_minutes=cmd.observation_minutes,
                instructions=cmd.instructions,
                external_prescriber=cmd.prescriber,
                external_jvpm=cmd.jvpm,
                created_at=now,
            )
            self._uow.applications.save_order(order)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "application.order_created", "ApplicationOrder", str(order.id),
                    subject=subject(patient.code, patient.full_name),
                    drug=order.drug, source=str(order.source), doses=order.doses_total,
                    prescriber=order.external_prescriber, jvpm=order.external_jvpm,
                )
            )
            self._uow.commit()
        return order


class CancelApplicationOrder:
    """Stop an order: its remaining doses won't be applied (what was given stays)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, order_id: ApplicationOrderId, reason: str
    ) -> ApplicationOrder:
        ensure_permission(actor, Permission.APPLICATIONS_ADMINISTER)
        with self._uow:
            order = _order(self._uow, order_id)
            now = self._clock.now()
            order.cancel(actor.user_id, reason, now)
            self._uow.applications.save_order(order)
            patient = self._uow.patients.get_by_id(order.patient_id)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "application.order_cancelled", "ApplicationOrder",
                    str(order.id),
                    subject=subject(patient.code, patient.full_name) if patient else None,
                    drug=order.drug, reason=order.cancel_reason,
                )
            )
            self._uow.commit()
        return order


# ── recording doses ───────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class RecordApplicationCommand:
    order_id: ApplicationOrderId
    outcome: ApplicationOutcome = ApplicationOutcome.APPLIED
    lot: str | None = None
    lot_expiry: date | None = None
    site: ApplicationSite | None = None
    blood_pressure: str | None = None
    temperature: float | None = None
    allergy_override: str | None = None
    notes: str | None = None


class RecordApplication:
    """Record the order's next dose: applied (opens the observation window) or not."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: RecordApplicationCommand) -> ApplicationRecord:
        ensure_permission(actor, Permission.APPLICATIONS_ADMINISTER)
        with self._uow:
            order = _order(self._uow, cmd.order_id)
            if not order.is_open:
                raise ApplicationOrderClosed(f"order {order.id} is {order.status}")
            patient = _patient(self._uow, order.patient_id)
            if patient.status != PatientStatus.ACTIVE:
                raise ValidationError("patient is inactive", code="application.patient_inactive")
            dose_number = order.next_dose(
                _settled(self._uow.applications.list_records_by_orders([order.id]))
            )
            if dose_number is None:  # defensive: an open order always has a next dose
                raise ApplicationOrderClosed(f"order {order.id} has no dose left")

            applied = cmd.outcome == ApplicationOutcome.APPLIED
            override = (cmd.allergy_override or "").strip() or None
            if applied:
                clashes = allergy_conflicts(order.drug, patient.allergies)
                if clashes and not override:
                    raise ValidationError(
                        f"{order.drug} may clash with the patient's allergies",
                        code="application.allergy_conflict", allergies=", ".join(clashes),
                    )
                if not clashes:
                    override = None
                today = clinic_now(self._uow, actor.tenant_id, self._clock).date()
                if cmd.lot_expiry and cmd.lot_expiry < today:
                    raise ValidationError("the lot is expired", code="application.lot_expired")

            now = self._clock.now()
            minutes = order.observation_minutes if applied else 0
            record = ApplicationRecord(
                id=ApplicationRecordId.new(),
                tenant_id=actor.tenant_id,
                order_id=order.id,
                patient_id=patient.id,
                dose_number=dose_number,
                outcome=cmd.outcome,
                recorded_at=now,
                recorded_by_id=actor.user_id,
                lot=cmd.lot,
                lot_expiry=cmd.lot_expiry,
                site=cmd.site,
                blood_pressure=cmd.blood_pressure,
                temperature=cmd.temperature,
                allergy_override=override if applied else None,
                notes=cmd.notes,
                observe_until=now + timedelta(minutes=minutes) if minutes else None,
            )
            self._uow.applications.save_record(record)
            _refresh(self._uow, order)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "application.recorded", "ApplicationRecord", str(record.id),
                    subject=subject(patient.code, patient.full_name),
                    drug=order.drug, dose=f"{dose_number}/{order.doses_total}",
                    status=str(record.outcome),
                    allergy_override=record.allergy_override,
                )
            )
            self._uow.commit()
        return record


class CloseObservation:
    """End the post-application observation: no reaction, or a described adverse reaction
    (which notifies the doctor who ordered it)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, record_id: ApplicationRecordId, reaction: bool,
        notes: str | None = None,
    ) -> ApplicationRecord:
        ensure_permission(actor, Permission.APPLICATIONS_ADMINISTER)
        with self._uow:
            record = _record(self._uow, record_id)
            now = self._clock.now()
            record.close_observation(actor.user_id, reaction, notes, now)
            self._uow.applications.save_record(record)
            order = _order(self._uow, record.order_id)
            patient = self._uow.patients.get_by_id(record.patient_id)
            label = subject(patient.code, patient.full_name) if patient else None
            if reaction:
                notify(
                    self._uow, actor, now, APPLICATION_REACTION, [order.ordered_by_id],
                    patient_id=str(record.patient_id),
                    patient_name=patient.full_name if patient else None,
                )
            self._uow.audit.append(
                audit_entry(
                    actor, now,
                    "application.reaction" if reaction else "application.observation_closed",
                    "ApplicationRecord", str(record.id), subject=label, drug=order.drug,
                    reason=record.reaction_notes,
                )
            )
            self._uow.commit()
        return record


class VoidApplication:
    """Void a wrong entry: it stays struck through in the history, and its dose is due again."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, record_id: ApplicationRecordId, reason: str
    ) -> ApplicationRecord:
        ensure_permission(actor, Permission.APPLICATIONS_ADMINISTER)
        with self._uow:
            record = _record(self._uow, record_id)
            now = self._clock.now()
            record.void(actor.user_id, reason, now)
            self._uow.applications.save_record(record)
            order = _order(self._uow, record.order_id)
            _refresh(self._uow, order)
            patient = self._uow.patients.get_by_id(record.patient_id)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "application.voided", "ApplicationRecord", str(record.id),
                    subject=subject(patient.code, patient.full_name) if patient else None,
                    drug=order.drug, reason=record.void_reason,
                )
            )
            self._uow.commit()
        return record


# ── reads ─────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class OrderView:
    order: ApplicationOrder
    records: list[ApplicationRecord]  # oldest first, voided included
    next_dose: int | None
    next_due_at: datetime | None
    allergy_conflicts: list[str]


def _views(uow: UnitOfWork, orders: list[ApplicationOrder],
           patients: dict[PatientId, Patient]) -> list[OrderView]:
    by_order: dict[ApplicationOrderId, list[ApplicationRecord]] = defaultdict(list)
    for r in uow.applications.list_records_by_orders([o.id for o in orders]):
        by_order[r.order_id].append(r)
    views = []
    for o in orders:
        records = by_order.get(o.id, [])
        n = o.next_dose(_settled(records)) if o.is_open else None
        patient = patients.get(o.patient_id)
        views.append(OrderView(
            order=o, records=records, next_dose=n,
            next_due_at=o.due_at(n) if n else None,
            allergy_conflicts=allergy_conflicts(o.drug, patient.allergies) if patient else [],
        ))
    return views


class GetPatientApplications:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[OrderView]:
        ensure_permission(actor, Permission.APPLICATIONS_VIEW)
        patient = _patient(self._uow, patient_id)
        orders = self._uow.applications.list_orders_by_patient(patient_id)
        return _views(self._uow, orders, {patient.id: patient})


@dataclass(frozen=True, slots=True)
class DueItem:
    patient: Patient
    view: OrderView
    late: bool


@dataclass(frozen=True, slots=True)
class RecordItem:
    patient: Patient
    order: ApplicationOrder
    record: ApplicationRecord


@dataclass(frozen=True, slots=True)
class ApplicationWorklist:
    now: datetime  # clinic wall-clock
    due: list[DueItem]  # next doses due today or earlier, earliest first
    observing: list[RecordItem]  # open observations, the one ending first on top
    done_today: list[RecordItem]  # recorded today (applied or not), newest first


class GetApplicationWorklist:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext) -> ApplicationWorklist:
        ensure_permission(actor, Permission.APPLICATIONS_VIEW)
        uow = self._uow
        now = clinic_now(uow, actor.tenant_id, self._clock)
        today_end = datetime.combine(now.date() + timedelta(days=1), time())
        patients: dict[PatientId, Patient] = {}

        def patient(pid: PatientId) -> Patient | None:
            if pid not in patients:
                p = uow.patients.get_by_id(pid)
                if p is not None:
                    patients[pid] = p
            return patients.get(pid)

        orders = uow.applications.list_open_orders()
        for o in orders:
            patient(o.patient_id)
        due = [
            DueItem(patients[v.order.patient_id], v, v.next_due_at < now - LATE_AFTER)
            for v in _views(uow, orders, patients)
            if v.next_due_at is not None and v.next_due_at < today_end
            and v.order.patient_id in patients
        ]
        due.sort(key=lambda i: i.view.next_due_at)

        order_cache = {o.id: o for o in orders}

        def items(records: list[ApplicationRecord]) -> list[RecordItem]:
            out = []
            for r in records:
                o = order_cache.get(r.order_id) or uow.applications.get_order(r.order_id)
                p = patient(r.patient_id)
                if o is not None and p is not None:
                    order_cache[o.id] = o
                    out.append(RecordItem(p, o, r))
            return out

        start = clinic_instant(uow, actor.tenant_id, self._clock,
                               datetime.combine(now.date(), time()))
        end = clinic_instant(uow, actor.tenant_id, self._clock, today_end)
        return ApplicationWorklist(
            now=now,
            due=due,
            observing=items(uow.applications.list_observing()),
            done_today=items(uow.applications.list_records_between(start, end)),
        )


# ── consultation drafts ───────────────────────────────────────────────────────────────────
# Adding/removing the drafts lives with the other consultation editors
# (``use_cases/consultations.py``); signing turns them into internal orders.
