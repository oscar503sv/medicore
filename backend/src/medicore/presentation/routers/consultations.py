"""Consultations router."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter

from medicore.application.use_cases.consultations import (
    AddApplicationDraft,
    AddDiagnosis,
    AddExam,
    AddPrescriptionDraft,
    AddProcedureDraft,
    AutosaveConsultation,
    ChangeNoteTemplate,
    ConsultationPatch,
    GetConsultation,
    GetConsultationVitals,
    RemoveApplicationDraft,
    RemoveDiagnosis,
    RemoveExam,
    RemovePrescriptionDraft,
    RemoveProcedureDraft,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
    UpdateConsultationVitals,
)
from medicore.domain.entities.application import ApplicationDraft
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.enums import SealStatus
from medicore.domain.shared.identifiers import AppointmentId, ConsultationId, ProcedureTypeId
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.presentation.dependencies import Actor, Clock, Codes, UoW
from medicore.presentation.schemas.consultations import (
    ApplicationDraftRequest,
    AutosaveRequest,
    ConsultationRefResponse,
    ConsultationResponse,
    ConsultationVitalsResponse,
    DiagnosisRequest,
    ExamRequestSchema,
    NoteTemplateRequest,
    PrescriptionDraftRequest,
    ProcedureDraftRequest,
    SignRequest,
    VitalsSchema,
    VitalsUpdateRequest,
)
from medicore.presentation.serializers import (
    ser_consultation,
    ser_consultation_ref,
    ser_consultation_vitals,
    ser_record,
)

router = APIRouter(prefix="/consultations", tags=["consultations"])

_DECIMAL_VITALS = ("temperature", "weight", "height")


def _vital_changes(v: VitalsSchema) -> dict[str, object]:
    """Only the fields the client sent: an absent field keeps what is stored, an explicit
    null (or empty string) clears it."""
    changes: dict[str, object] = {}
    for name in v.model_fields_set:
        value = getattr(v, name)
        if name in _DECIMAL_VITALS:
            value = Decimal(value) if value else None
        changes[name] = value
    return changes


@router.post("/start/{appointment_id}", response_model=ConsultationRefResponse, status_code=201)
def start_consultation(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    c = StartConsultation(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    return ser_consultation_ref(c)


@router.get(
    "/by-appointment/{appointment_id}/vitals", response_model=ConsultationVitalsResponse
)
def get_consultation_vitals(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    view = GetConsultationVitals(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    return ser_consultation_vitals(view)


@router.put("/{consultation_id}/vitals", response_model=ConsultationVitalsResponse)
def update_consultation_vitals(
    consultation_id: str, body: VitalsUpdateRequest, actor: Actor, uow: UoW, clock: Clock
):
    view = UpdateConsultationVitals(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), _vital_changes(body)
    )
    return ser_consultation_vitals(view)


@router.get("/{consultation_id}", response_model=ConsultationResponse)
def get_consultation(consultation_id: str, actor: Actor, uow: UoW, clock: Clock):
    c = GetConsultation(uow, clock).execute(actor, ConsultationId.parse(consultation_id))
    return ser_consultation(c, uow)


@router.patch("/{consultation_id}/autosave", response_model=ConsultationResponse)
def autosave(consultation_id: str, body: AutosaveRequest, actor: Actor, uow: UoW, clock: Clock):
    c = AutosaveConsultation(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id),
        ConsultationPatch(
            vitals=_vital_changes(body.vitals) if body.vitals else None, note=body.note
        ),
    )
    return ser_consultation(c, uow)


@router.post("/{consultation_id}/note-template", response_model=ConsultationResponse)
def change_note_template(
    consultation_id: str, body: NoteTemplateRequest, actor: Actor, uow: UoW, clock: Clock
):
    c = ChangeNoteTemplate(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), body.template
    )
    return ser_consultation(c, uow)


@router.post("/{consultation_id}/diagnoses", response_model=ConsultationResponse)
def add_diagnosis(
    consultation_id: str, body: DiagnosisRequest, actor: Actor, uow: UoW, clock: Clock
):
    c = AddDiagnosis(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), IcdCode(body.code, body.label)
    )
    return ser_consultation(c, uow)


@router.delete("/{consultation_id}/diagnoses/{code}", response_model=ConsultationResponse)
def remove_diagnosis(consultation_id: str, code: str, actor: Actor, uow: UoW, clock: Clock):
    c = RemoveDiagnosis(uow, clock).execute(actor, ConsultationId.parse(consultation_id), code)
    return ser_consultation(c, uow)


@router.post("/{consultation_id}/prescriptions", response_model=ConsultationResponse)
def add_prescription(
    consultation_id: str, body: PrescriptionDraftRequest, actor: Actor, uow: UoW, clock: Clock
):
    draft = PrescriptionDraft(
        drug=body.drug, dose=body.dose, schedule=body.schedule, duration_days=body.duration_days
    )
    c = AddPrescriptionDraft(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), draft
    )
    return ser_consultation(c, uow)


@router.delete("/{consultation_id}/prescriptions/{index}", response_model=ConsultationResponse)
def remove_prescription(
    consultation_id: str, index: int, actor: Actor, uow: UoW, clock: Clock
):
    c = RemovePrescriptionDraft(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), index
    )
    return ser_consultation(c, uow)


@router.post("/{consultation_id}/applications", response_model=ConsultationResponse)
def add_application(
    consultation_id: str, body: ApplicationDraftRequest, actor: Actor, uow: UoW, clock: Clock
):
    draft = ApplicationDraft(
        drug=body.drug, dose=body.dose, route=body.route, doses_total=body.doses_total,
        interval_hours=body.interval_hours, observation_minutes=body.observation_minutes,
        instructions=body.instructions,
    )
    c = AddApplicationDraft(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), draft
    )
    return ser_consultation(c, uow)


@router.delete("/{consultation_id}/applications/{index}", response_model=ConsultationResponse)
def remove_application(
    consultation_id: str, index: int, actor: Actor, uow: UoW, clock: Clock
):
    c = RemoveApplicationDraft(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), index
    )
    return ser_consultation(c, uow)


@router.post("/{consultation_id}/procedures", response_model=ConsultationResponse)
def add_procedure(
    consultation_id: str, body: ProcedureDraftRequest, actor: Actor, uow: UoW, clock: Clock
):
    c = AddProcedureDraft(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), ProcedureTypeId.parse(body.type_id),
        body.indication, body.included,
    )
    return ser_consultation(c, uow)


@router.delete("/{consultation_id}/procedures/{index}", response_model=ConsultationResponse)
def remove_procedure(
    consultation_id: str, index: int, actor: Actor, uow: UoW, clock: Clock
):
    c = RemoveProcedureDraft(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), index
    )
    return ser_consultation(c, uow)


@router.post("/{consultation_id}/exams", response_model=ConsultationResponse)
def add_exam(
    consultation_id: str, body: ExamRequestSchema, actor: Actor, uow: UoW, clock: Clock
):
    exam = ExamRequest(name=body.name, kind=body.kind, notes=body.notes)
    c = AddExam(uow, clock).execute(actor, ConsultationId.parse(consultation_id), exam)
    return ser_consultation(c, uow)


@router.delete("/{consultation_id}/exams/{index}", response_model=ConsultationResponse)
def remove_exam(consultation_id: str, index: int, actor: Actor, uow: UoW, clock: Clock):
    c = RemoveExam(uow, clock).execute(actor, ConsultationId.parse(consultation_id), index)
    return ser_consultation(c, uow)


@router.post("/{consultation_id}/sign")
def sign_consultation(
    consultation_id: str, body: SignRequest, actor: Actor, uow: UoW, codes: Codes, clock: Clock
):
    cmd = SignConsultationCommand(
        consultation_id=ConsultationId.parse(consultation_id),
        chief_complaint=body.chief_complaint,
    )
    record = SignConsultation(uow, codes, clock).execute(actor, cmd)
    return ser_record(record, integrity=SealStatus.OK)
