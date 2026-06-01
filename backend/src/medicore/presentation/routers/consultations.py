"""Consultations router."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter

from medicore.application.use_cases.consultations import (
    AddDiagnosis,
    AddPrescriptionDraft,
    AutosaveConsultation,
    ConsultationPatch,
    RemoveDiagnosis,
    RemovePrescriptionDraft,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.enums import RecordType
from medicore.domain.shared.identifiers import AppointmentId, ConsultationId
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.vitals import Vitals
from medicore.presentation.dependencies import Actor, Clock, Codes, UoW
from medicore.presentation.schemas.consultations import (
    AutosaveRequest,
    ConsultationResponse,
    DiagnosisRequest,
    PrescriptionDraftRequest,
    SignRequest,
)
from medicore.presentation.serializers import ser_consultation, ser_record

router = APIRouter(prefix="/consultations", tags=["consultations"])


@router.post("/start/{appointment_id}", response_model=ConsultationResponse, status_code=201)
def start_consultation(appointment_id: str, actor: Actor, uow: UoW, clock: Clock):
    c = StartConsultation(uow, clock).execute(actor, AppointmentId.parse(appointment_id))
    return ser_consultation(c)


@router.patch("/{consultation_id}/autosave", response_model=ConsultationResponse)
def autosave(consultation_id: str, body: AutosaveRequest, actor: Actor, uow: UoW, clock: Clock):
    vitals = None
    if body.vitals:
        v = body.vitals
        vitals = Vitals(
            blood_pressure=v.blood_pressure,
            heart_rate=v.heart_rate,
            spo2=v.spo2,
            temperature=Decimal(v.temperature) if v.temperature else None,
            weight=Decimal(v.weight) if v.weight else None,
            glucose=v.glucose,
            height=Decimal(v.height) if v.height else None,
            fetal_heart_rate=v.fetal_heart_rate,
        )
    soap = None
    if body.soap:
        s = body.soap
        soap = SoapNote(
            subjective=s.subjective,
            objective=s.objective,
            assessment=s.assessment,
            plan=s.plan,
        )
    c = AutosaveConsultation(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), ConsultationPatch(vitals=vitals, soap=soap)
    )
    return ser_consultation(c)


@router.post("/{consultation_id}/diagnoses", response_model=ConsultationResponse)
def add_diagnosis(
    consultation_id: str, body: DiagnosisRequest, actor: Actor, uow: UoW, clock: Clock
):
    c = AddDiagnosis(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), IcdCode(body.code, body.label)
    )
    return ser_consultation(c)


@router.delete("/{consultation_id}/diagnoses/{code}", response_model=ConsultationResponse)
def remove_diagnosis(consultation_id: str, code: str, actor: Actor, uow: UoW, clock: Clock):
    c = RemoveDiagnosis(uow, clock).execute(actor, ConsultationId.parse(consultation_id), code)
    return ser_consultation(c)


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
    return ser_consultation(c)


@router.delete("/{consultation_id}/prescriptions/{index}", response_model=ConsultationResponse)
def remove_prescription(
    consultation_id: str, index: int, actor: Actor, uow: UoW, clock: Clock
):
    c = RemovePrescriptionDraft(uow, clock).execute(
        actor, ConsultationId.parse(consultation_id), index
    )
    return ser_consultation(c)


@router.post("/{consultation_id}/sign")
def sign_consultation(
    consultation_id: str, body: SignRequest, actor: Actor, uow: UoW, codes: Codes, clock: Clock
):
    cmd = SignConsultationCommand(
        consultation_id=ConsultationId.parse(consultation_id),
        record_type=RecordType(body.record_type),
        chief_complaint=body.chief_complaint,
    )
    record = SignConsultation(uow, codes, clock).execute(actor, cmd)
    return ser_record(record)
