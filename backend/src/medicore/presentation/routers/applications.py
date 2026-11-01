"""In-clinic medication applications router: worklist, patient orders, external orders,
recording doses, observation and voiding."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.applications import (
    CancelApplicationOrder,
    CloseObservation,
    CreateExternalOrder,
    CreateExternalOrderCommand,
    GetApplicationWorklist,
    GetPatientApplications,
    OrderView,
    RecordApplication,
    RecordApplicationCommand,
    VoidApplication,
)
from medicore.domain.entities.application import ApplicationOrder, ApplicationRecord
from medicore.domain.entities.patient import Patient
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    PatientId,
    UserId,
)
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.applications import (
    ApplicationOrderResponse,
    ApplicationRecordResponse,
    ApplicationWorklistResponse,
    CloseObservationRequest,
    ExternalOrderRequest,
    ReasonRequest,
    RecordApplicationRequest,
)

router = APIRouter(prefix="/applications", tags=["applications"])


class _Names:
    """Resolves user ids to display names once per request."""

    def __init__(self, uow) -> None:
        self._uow = uow
        self._cache: dict[UserId, str | None] = {}

    def __call__(self, uid: UserId | None) -> str | None:
        if uid is None:
            return None
        if uid not in self._cache:
            user = self._uow.users.get_by_id(uid)
            self._cache[uid] = user.name if user else None
        return self._cache[uid]


def _ser_record(r: ApplicationRecord, name: _Names) -> dict:
    return {
        "id": str(r.id),
        "order_id": str(r.order_id),
        "dose_number": r.dose_number,
        "outcome": str(r.outcome),
        "recorded_at": r.recorded_at,
        "recorded_by_name": name(r.recorded_by_id),
        "lot": r.lot,
        "lot_expiry": r.lot_expiry,
        "site": str(r.site) if r.site else None,
        "blood_pressure": r.blood_pressure,
        "temperature": r.temperature,
        "allergy_override": r.allergy_override,
        "notes": r.notes,
        "observe_until": r.observe_until,
        "observation_closed_at": r.observation_closed_at,
        "observation_closed_by_name": name(r.observation_closed_by_id),
        "reaction": r.reaction,
        "reaction_notes": r.reaction_notes,
        "voided_at": r.voided_at,
        "voided_by_name": name(r.voided_by_id),
        "void_reason": r.void_reason,
    }


def _ser_order(o: ApplicationOrder, name: _Names, view: OrderView | None = None) -> dict:
    return {
        "id": str(o.id),
        "patient_id": str(o.patient_id),
        "drug": o.drug,
        "dose": o.dose,
        "route": str(o.route),
        "source": str(o.source),
        "status": str(o.status),
        "starts_at": o.starts_at,
        "doses_total": o.doses_total,
        "interval_hours": o.interval_hours,
        "observation_minutes": o.observation_minutes,
        "instructions": o.instructions,
        "ordered_by_name": name(o.ordered_by_id),
        "external_prescriber": o.external_prescriber,
        "external_jvpm": o.external_jvpm,
        "created_by_name": name(o.created_by_id),
        "created_at": o.created_at,
        "cancelled_at": o.cancelled_at,
        "cancelled_by_name": name(o.cancelled_by_id),
        "cancel_reason": o.cancel_reason,
        "next_dose": view.next_dose if view else None,
        "next_due_at": view.next_due_at if view else None,
        "allergy_conflicts": view.allergy_conflicts if view else [],
        "records": [_ser_record(r, name) for r in view.records] if view else [],
    }


def _ser_patient(p: Patient) -> dict:
    return {
        "id": str(p.id), "code": p.code, "name": p.full_name, "age": p.age(),
        "allergies": list(p.allergies),
    }


@router.get("/worklist", response_model=ApplicationWorklistResponse)
def worklist(actor: Actor, uow: UoW, clock: Clock):
    with uow:
        wl = GetApplicationWorklist(uow, clock).execute(actor)
        name = _Names(uow)

        def rec_item(i) -> dict:
            return {"patient": _ser_patient(i.patient), "order": _ser_order(i.order, name),
                    "record": _ser_record(i.record, name)}

        return {
            "now": wl.now,
            "due": [
                {
                    "patient": _ser_patient(i.patient),
                    "order": _ser_order(i.view.order, name, i.view),
                    "late": i.late,
                }
                for i in wl.due
            ],
            "observing": [rec_item(i) for i in wl.observing],
            "done_today": [rec_item(i) for i in wl.done_today],
        }


@router.get("/patients/{patient_id}", response_model=list[ApplicationOrderResponse])
def patient_orders(patient_id: str, actor: Actor, uow: UoW):
    with uow:
        views = GetPatientApplications(uow).execute(actor, PatientId.parse(patient_id))
        name = _Names(uow)
        return [_ser_order(v.order, name, v) for v in views]


@router.post("/orders", response_model=ApplicationOrderResponse, status_code=201)
def create_external_order(body: ExternalOrderRequest, actor: Actor, uow: UoW, clock: Clock):
    order = CreateExternalOrder(uow, clock).execute(
        actor,
        CreateExternalOrderCommand(
            patient_id=PatientId.parse(body.patient_id), drug=body.drug, dose=body.dose,
            route=body.route, prescriber=body.prescriber, jvpm=body.jvpm,
            doses_total=body.doses_total, interval_hours=body.interval_hours,
            observation_minutes=body.observation_minutes, instructions=body.instructions,
        ),
    )
    return _ser_order(order, _Names(uow))


@router.post("/orders/{order_id}/cancel", response_model=ApplicationOrderResponse)
def cancel_order(order_id: str, body: ReasonRequest, actor: Actor, uow: UoW, clock: Clock):
    order = CancelApplicationOrder(uow, clock).execute(
        actor, ApplicationOrderId.parse(order_id), body.reason
    )
    return _ser_order(order, _Names(uow))


@router.post(
    "/orders/{order_id}/records", response_model=ApplicationRecordResponse, status_code=201
)
def record_dose(
    order_id: str, body: RecordApplicationRequest, actor: Actor, uow: UoW, clock: Clock
):
    record = RecordApplication(uow, clock).execute(
        actor,
        RecordApplicationCommand(
            order_id=ApplicationOrderId.parse(order_id), outcome=body.outcome, lot=body.lot,
            lot_expiry=body.lot_expiry, site=body.site, blood_pressure=body.blood_pressure,
            temperature=body.temperature, allergy_override=body.allergy_override,
            notes=body.notes,
        ),
    )
    return _ser_record(record, _Names(uow))


@router.post("/records/{record_id}/observation", response_model=ApplicationRecordResponse)
def close_observation(
    record_id: str, body: CloseObservationRequest, actor: Actor, uow: UoW, clock: Clock
):
    record = CloseObservation(uow, clock).execute(
        actor, ApplicationRecordId.parse(record_id), body.reaction, body.notes
    )
    return _ser_record(record, _Names(uow))


@router.post("/records/{record_id}/void", response_model=ApplicationRecordResponse)
def void_record(record_id: str, body: ReasonRequest, actor: Actor, uow: UoW, clock: Clock):
    record = VoidApplication(uow, clock).execute(
        actor, ApplicationRecordId.parse(record_id), body.reason
    )
    return _ser_record(record, _Names(uow))
