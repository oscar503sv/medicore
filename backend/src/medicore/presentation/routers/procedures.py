"""Minor procedures router: the clinic's catalog, the worklist, a patient's procedures and
each procedure's lifecycle (progress, consent, sign, cancel, amend)."""

from __future__ import annotations

from dataclasses import fields

from fastapi import APIRouter

from medicore.application.use_cases.procedures import (
    AmendProcedure,
    CancelProcedure,
    CreateProcedure,
    CreateProcedureCommand,
    CreateProcedureType,
    GetPatientProcedures,
    GetProcedure,
    GetProcedureCatalog,
    GetProcedureWorklist,
    ProcedureTypeCommand,
    RecordProcedureConsent,
    SaveProcedureProgress,
    SetProcedureTypeActive,
    SignProcedure,
    UpdateProcedureType,
)
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.procedure import Procedure, ProcedureProgress, ProcedureType
from medicore.domain.shared.identifiers import (
    AppointmentId,
    PatientId,
    ProcedureId,
    ProcedureTypeId,
)
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.routers.applications import _Names
from medicore.presentation.schemas.procedures import (
    ActiveRequest,
    AmendRequest,
    ConsentRequest,
    CreateProcedureRequest,
    ProcedureDetailResponse,
    ProcedureResponse,
    ProcedureTypeRequest,
    ProcedureTypeResponse,
    ProcedureWorklistResponse,
    ProgressRequest,
    ReasonRequest,
)

router = APIRouter(prefix="/procedures", tags=["procedures"])

_PROGRESS_FIELDS = [f.name for f in fields(ProcedureProgress)]


def _ser_type(t: ProcedureType) -> dict:
    return {
        "id": str(t.id), "name": t.name, "performer": str(t.performer),
        "requires_consent": t.requires_consent, "follow_up_days": t.follow_up_days,
        "takes_specimen": t.takes_specimen, "technique_template": t.technique_template,
        "instructions_template": t.instructions_template, "active": t.active,
    }


def _ser(p: Procedure, name: _Names) -> dict:
    return {
        "id": str(p.id),
        "patient_id": str(p.patient_id),
        "type_id": str(p.type_id),
        "type_name": p.type_name,
        "performer": str(p.performer),
        "requires_consent": p.requires_consent,
        "source": str(p.source),
        "indication": p.indication,
        "ordered_by_name": name(p.ordered_by_id),
        "created_by_name": name(p.created_by_id),
        "follow_up_days": p.follow_up_days,
        "takes_specimen": p.takes_specimen,
        "consultation_id": str(p.consultation_id) if p.consultation_id else None,
        "appointment_id": str(p.appointment_id) if p.appointment_id else None,
        "created_at": p.created_at,
        "status": str(p.status),
        "consent_signer": p.consent_signer,
        "consent_relationship": p.consent_relationship,
        "consent_witness": p.consent_witness,
        "consent_at": p.consent_at,
        "consent_by_name": name(p.consent_by_id),
        **{f: getattr(p, f) for f in _PROGRESS_FIELDS},
        "started_at": p.started_at,
        "performed_at": p.performed_at,
        "performed_by_name": name(p.performed_by_id),
        "follow_up_on": p.follow_up_on,
        "cancelled_at": p.cancelled_at,
        "cancelled_by_name": name(p.cancelled_by_id),
        "cancel_reason": p.cancel_reason,
        "amendments": [
            {"at": a.at, "by_name": name(a.by_id), "text": a.text, "reason": a.reason}
            for a in p.amendments
        ],
    }


def _ser_patient(p: Patient) -> dict:
    return {
        "id": str(p.id), "code": p.code, "name": p.full_name, "age": p.age(),
        "allergies": list(p.allergies),
    }


def _type_cmd(body: ProcedureTypeRequest) -> ProcedureTypeCommand:
    return ProcedureTypeCommand(
        name=body.name, performer=body.performer, requires_consent=body.requires_consent,
        follow_up_days=body.follow_up_days, takes_specimen=body.takes_specimen,
        technique_template=body.technique_template,
        instructions_template=body.instructions_template,
    )


# ── catalog ───────────────────────────────────────────────────────────────────────────────
@router.get("/catalog", response_model=list[ProcedureTypeResponse])
def catalog(actor: Actor, uow: UoW, clock: Clock):
    return [_ser_type(t) for t in GetProcedureCatalog(uow, clock).execute(actor)]


@router.post("/catalog", response_model=ProcedureTypeResponse, status_code=201)
def create_type(body: ProcedureTypeRequest, actor: Actor, uow: UoW, clock: Clock):
    return _ser_type(CreateProcedureType(uow, clock).execute(actor, _type_cmd(body)))


@router.put("/catalog/{type_id}", response_model=ProcedureTypeResponse)
def update_type(type_id: str, body: ProcedureTypeRequest, actor: Actor, uow: UoW, clock: Clock):
    kind = UpdateProcedureType(uow, clock).execute(
        actor, ProcedureTypeId.parse(type_id), _type_cmd(body)
    )
    return _ser_type(kind)


@router.post("/catalog/{type_id}/active", response_model=ProcedureTypeResponse)
def set_type_active(type_id: str, body: ActiveRequest, actor: Actor, uow: UoW, clock: Clock):
    kind = SetProcedureTypeActive(uow, clock).execute(
        actor, ProcedureTypeId.parse(type_id), body.active
    )
    return _ser_type(kind)


# ── reads ─────────────────────────────────────────────────────────────────────────────────
@router.get("/worklist", response_model=ProcedureWorklistResponse)
def worklist(actor: Actor, uow: UoW, clock: Clock):
    with uow:
        wl = GetProcedureWorklist(uow, clock).execute(actor)
        name = _Names(uow)

        def item(i) -> dict:
            return {"patient": _ser_patient(i.patient), "procedure": _ser(i.procedure, name)}

        return {
            "now": wl.now,
            "pending": [item(i) for i in wl.pending],
            "today": [
                {
                    "appointment_id": str(i.appointment.id),
                    "scheduled_start": i.appointment.scheduled_start,
                    "status": str(i.appointment.status),
                    "reason": i.appointment.reason,
                    "doctor_name": name(i.appointment.doctor_id),
                    "patient": _ser_patient(i.patient),
                    "procedure": _ser(i.procedure, name) if i.procedure else None,
                }
                for i in wl.today
            ],
            "done": [item(i) for i in wl.done],
        }


@router.get("/patients/{patient_id}", response_model=list[ProcedureResponse])
def patient_procedures(patient_id: str, actor: Actor, uow: UoW):
    with uow:
        items = GetPatientProcedures(uow).execute(actor, PatientId.parse(patient_id))
        name = _Names(uow)
        return [_ser(p, name) for p in items]


def _detail(uow, actor, procedure_id: ProcedureId) -> dict:
    with uow:
        view = GetProcedure(uow).execute(actor, procedure_id)
        return {
            "procedure": _ser(view.procedure, _Names(uow)),
            "patient": _ser_patient(view.patient),
            "technique_template": view.kind.technique_template if view.kind else None,
            "instructions_template": view.kind.instructions_template if view.kind else None,
            "allergy_conflicts": view.allergy_conflicts,
        }


@router.get("/{procedure_id}", response_model=ProcedureDetailResponse)
def get_procedure(procedure_id: str, actor: Actor, uow: UoW):
    return _detail(uow, actor, ProcedureId.parse(procedure_id))


# ── lifecycle (each returns the refreshed detail) ─────────────────────────────────────────
@router.post("", response_model=ProcedureDetailResponse, status_code=201)
def create_procedure(body: CreateProcedureRequest, actor: Actor, uow: UoW, clock: Clock):
    procedure = CreateProcedure(uow, clock).execute(actor, CreateProcedureCommand(
        patient_id=PatientId.parse(body.patient_id), type_id=ProcedureTypeId.parse(body.type_id),
        indication=body.indication,
        appointment_id=AppointmentId.parse(body.appointment_id) if body.appointment_id else None,
    ))
    return _detail(uow, actor, procedure.id)


@router.put("/{procedure_id}", response_model=ProcedureDetailResponse)
def save_progress(procedure_id: str, body: ProgressRequest, actor: Actor, uow: UoW,
                  clock: Clock):
    pid = ProcedureId.parse(procedure_id)
    SaveProcedureProgress(uow, clock).execute(
        actor, pid, ProcedureProgress(**body.model_dump(include=set(_PROGRESS_FIELDS)))
    )
    return _detail(uow, actor, pid)


@router.post("/{procedure_id}/consent", response_model=ProcedureDetailResponse)
def record_consent(procedure_id: str, body: ConsentRequest, actor: Actor, uow: UoW,
                   clock: Clock):
    pid = ProcedureId.parse(procedure_id)
    RecordProcedureConsent(uow, clock).execute(
        actor, pid, body.signer, body.relationship, body.witness
    )
    return _detail(uow, actor, pid)


@router.post("/{procedure_id}/sign", response_model=ProcedureDetailResponse)
def sign(procedure_id: str, actor: Actor, uow: UoW, clock: Clock):
    pid = ProcedureId.parse(procedure_id)
    SignProcedure(uow, clock).execute(actor, pid)
    return _detail(uow, actor, pid)


@router.post("/{procedure_id}/cancel", response_model=ProcedureDetailResponse)
def cancel(procedure_id: str, body: ReasonRequest, actor: Actor, uow: UoW, clock: Clock):
    pid = ProcedureId.parse(procedure_id)
    CancelProcedure(uow, clock).execute(actor, pid, body.reason)
    return _detail(uow, actor, pid)


@router.post("/{procedure_id}/amendments", response_model=ProcedureDetailResponse)
def amend(procedure_id: str, body: AmendRequest, actor: Actor, uow: UoW, clock: Clock):
    pid = ProcedureId.parse(procedure_id)
    AmendProcedure(uow, clock).execute(actor, pid, body.text, body.reason)
    return _detail(uow, actor, pid)
