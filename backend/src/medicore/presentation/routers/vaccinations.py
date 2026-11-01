"""Vaccinations router: national catalog/schedule, patient card, records and worklist."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.use_cases.vaccinations import (
    GetVaccinationCard,
    GetVaccinationWorklist,
    RecordVaccination,
    RecordVaccinationCommand,
    VoidVaccination,
    WorklistItem,
)
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.services.immunization import SCHEDULE, SCHEDULE_NAME, VACCINES
from medicore.domain.shared.identifiers import PatientId, UserId, VaccinationRecordId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.vaccinations import (
    RecordVaccinationRequest,
    VaccinationCardResponse,
    VaccinationCatalogResponse,
    VaccinationRecordResponse,
    VaccinationWorklistResponse,
    VoidVaccinationRequest,
)

router = APIRouter(prefix="/vaccinations", tags=["vaccinations"])


def _names(uow, ids: set[UserId]) -> dict[UserId, str]:
    out: dict[UserId, str] = {}
    for uid in ids:
        user = uow.users.get_by_id(uid)
        if user:
            out[uid] = user.name
    return out


def _ser_records(uow, records: list[VaccinationRecord]) -> list[dict]:
    ids = {r.recorded_by_id for r in records} | {r.voided_by_id for r in records if r.voided_by_id}
    names = _names(uow, ids)
    return [
        {
            "id": str(r.id),
            "patient_id": str(r.patient_id),
            "vaccine_code": r.vaccine_code,
            "dose_key": r.dose_key,
            "outcome": str(r.outcome),
            "occurred_on": r.occurred_on,
            "source": str(r.source),
            "lot": r.lot,
            "route": str(r.route) if r.route else None,
            "site": str(r.site) if r.site else None,
            "notes": r.notes,
            "recorded_by_id": str(r.recorded_by_id),
            "recorded_by_name": names.get(r.recorded_by_id),
            "created_at": r.created_at,
            "voided_at": r.voided_at,
            "voided_by_name": names.get(r.voided_by_id) if r.voided_by_id else None,
            "void_reason": r.void_reason,
        }
        for r in records
    ]


def _ser_patient(p: Patient) -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.full_name,
        "age": p.age(),
        "date_of_birth": p.date_of_birth,
        "sex": str(p.sex),
        "phone": p.contact.phone,
    }


def _ser_item(i: WorklistItem) -> dict:
    return {
        "patient": _ser_patient(i.patient),
        "key": i.state.dose.key,
        "vaccine": i.state.dose.vaccine,
        "status": i.state.status,
        "due_on": i.state.due_on,
    }


@router.get("/catalog", response_model=VaccinationCatalogResponse)
def catalog(actor: Actor):
    ensure_permission(actor, Permission.VACCINATIONS_VIEW)
    return {
        "schedule": SCHEDULE_NAME,
        "vaccines": [
            {"code": v.code, "route": str(v.route), "in_schedule": v.in_schedule}
            for v in VACCINES.values()
        ],
        "doses": [
            {
                "key": d.key, "vaccine": d.vaccine, "kind": d.kind, "number": d.number,
                "age_months": d.age_months, "stage": d.stage,
                "max_age_months": d.max_age_months, "repeat_months": d.repeat_months,
                "routine": d.routine, "sex": str(d.sex) if d.sex else None,
            }
            for d in SCHEDULE
        ],
    }


@router.get("/worklist", response_model=VaccinationWorklistResponse)
def worklist(actor: Actor, uow: UoW, clock: Clock, horizon_days: int = Query(30, ge=1, le=180)):
    with uow:
        wl = GetVaccinationWorklist(uow, clock).execute(actor, horizon_days)
        given = _ser_records(uow, [r for _, r in wl.given_today])
    return {
        "today": wl.today,
        "pending": [_ser_item(i) for i in wl.pending],
        "upcoming": [_ser_item(i) for i in wl.upcoming],
        "given_today": [
            {"patient": _ser_patient(p), "record": rec}
            for (p, _), rec in zip(wl.given_today, given, strict=True)
        ],
    }


@router.get("/patients/{patient_id}", response_model=VaccinationCardResponse)
def patient_card(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    with uow:
        card = GetVaccinationCard(uow, clock).execute(actor, PatientId.parse(patient_id))
        records = _ser_records(uow, card.records)
    return {
        "today": card.today,
        "states": [
            {"key": s.dose.key, "status": s.status, "due_on": s.due_on, "last_on": s.last_on}
            for s in card.states
        ],
        "records": records,
    }


@router.post(
    "/patients/{patient_id}", response_model=VaccinationRecordResponse, status_code=201
)
def record_vaccination(
    patient_id: str, body: RecordVaccinationRequest, actor: Actor, uow: UoW, clock: Clock
):
    cmd = RecordVaccinationCommand(
        patient_id=PatientId.parse(patient_id),
        vaccine_code=body.vaccine_code,
        dose_key=body.dose_key,
        outcome=body.outcome,
        occurred_on=body.occurred_on,
        source=body.source,
        lot=body.lot,
        route=body.route,
        site=body.site,
        notes=body.notes,
    )
    record = RecordVaccination(uow, clock).execute(actor, cmd)
    with uow:
        return _ser_records(uow, [record])[0]


@router.post("/{record_id}/void", response_model=VaccinationRecordResponse)
def void_vaccination(
    record_id: str, body: VoidVaccinationRequest, actor: Actor, uow: UoW, clock: Clock
):
    record = VoidVaccination(uow, clock).execute(
        actor, VaccinationRecordId.parse(record_id), body.reason
    )
    with uow:
        return _ser_records(uow, [record])[0]
