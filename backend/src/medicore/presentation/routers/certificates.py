"""Medical certificates router: issued from a signed record, listed, voided."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.certificates import (
    IssueCertificateCommand,
    IssueMedicalCertificate,
    ListMedicalCertificates,
    VoidMedicalCertificate,
)
from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.shared.identifiers import CertificateId, PatientId, RecordId
from medicore.presentation.dependencies import Actor, Clock, Codes, UoW
from medicore.presentation.schemas.certificates import (
    CertificateResponse,
    IssueCertificateRequest,
    VoidCertificateRequest,
)

router = APIRouter(tags=["certificates"])


def _ser(c: MedicalCertificate, uow) -> dict:
    doctor = uow.users.get_by_id(c.doctor_id)
    return {
        "id": str(c.id),
        "code": c.code,
        "patient_id": str(c.patient_id),
        "record_id": str(c.record_id),
        "doctor_id": str(c.doctor_id),
        "doctor_name": doctor.name if doctor else None,
        "kind": c.kind,
        "issued_at": c.issued_at,
        "rest_from": c.rest_from,
        "rest_days": c.rest_days,
        "rest_until": c.rest_until,
        "diagnosis": c.diagnosis,
        "remarks": c.remarks,
        "addressee": c.addressee,
        "voided_at": c.voided_at,
        "void_reason": c.void_reason,
    }


@router.post("/records/{record_id}/certificates", response_model=CertificateResponse,
             status_code=201)
def issue_certificate(
    record_id: str, body: IssueCertificateRequest, actor: Actor, uow: UoW, codes: Codes,
    clock: Clock,
):
    cmd = IssueCertificateCommand(
        record_id=RecordId.parse(record_id), kind=body.kind, rest_from=body.rest_from,
        rest_days=body.rest_days, include_diagnosis=body.include_diagnosis,
        remarks=body.remarks, addressee=body.addressee,
    )
    certificate = IssueMedicalCertificate(uow, codes, clock).execute(actor, cmd)
    return _ser(certificate, uow)


@router.get("/records/{record_id}/certificates", response_model=list[CertificateResponse])
def record_certificates(record_id: str, actor: Actor, uow: UoW):
    with uow:
        items = ListMedicalCertificates(uow).execute(actor, record_id=RecordId.parse(record_id))
        return [_ser(c, uow) for c in items]


@router.get("/patients/{patient_id}/certificates", response_model=list[CertificateResponse])
def patient_certificates(patient_id: str, actor: Actor, uow: UoW):
    with uow:
        items = ListMedicalCertificates(uow).execute(
            actor, patient_id=PatientId.parse(patient_id)
        )
        return [_ser(c, uow) for c in items]


@router.post("/certificates/{certificate_id}/void", response_model=CertificateResponse)
def void_certificate(
    certificate_id: str, body: VoidCertificateRequest, actor: Actor, uow: UoW, clock: Clock
):
    certificate = VoidMedicalCertificate(uow, clock).execute(
        actor, CertificateId.parse(certificate_id), body.reason
    )
    return _ser(certificate, uow)
