"""Prescriptions router. Listing follows records.view; lifecycle actions require
prescriptions.manage (enforced in the use cases)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.prescriptions import (
    CancelPrescription,
    CompletePrescription,
    ListPatientPrescriptions,
)
from medicore.domain.shared.identifiers import PatientId, PrescriptionId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.prescriptions import (
    PrescriptionListResponse,
    PrescriptionResponse,
)
from medicore.presentation.serializers import ser_prescription

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.get("", response_model=PrescriptionListResponse)
def list_prescriptions(actor: Actor, uow: UoW, patient_id: str = Query(...)):
    with uow:
        views = ListPatientPrescriptions(uow).execute(actor, PatientId.parse(patient_id))
    return PrescriptionListResponse(
        items=[ser_prescription(v.prescription, v.prescriber_name) for v in views]
    )


@router.post("/{prescription_id}/complete", response_model=PrescriptionResponse)
def complete_prescription(prescription_id: str, actor: Actor, uow: UoW, clock: Clock):
    prescription = CompletePrescription(uow, clock).execute(
        actor, PrescriptionId.parse(prescription_id)
    )
    return ser_prescription(prescription)


@router.post("/{prescription_id}/cancel", response_model=PrescriptionResponse)
def cancel_prescription(prescription_id: str, actor: Actor, uow: UoW, clock: Clock):
    prescription = CancelPrescription(uow, clock).execute(
        actor, PrescriptionId.parse(prescription_id)
    )
    return ser_prescription(prescription)
