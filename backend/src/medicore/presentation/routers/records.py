"""Medical records and documents router."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.records import (
    AmendMedicalRecord,
    GetMedicalRecord,
    ListMedicalRecords,
    ListPatientDocuments,
    UploadDocument,
    UploadDocumentCommand,
)
from medicore.domain.enums import DocumentKind
from medicore.domain.repositories._support import RecordFilter
from medicore.domain.shared.identifiers import PatientId, RecordId
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.records import (
    AmendRequest,
    DocumentResponse,
    RecordResponse,
    UploadDocumentRequest,
)
from medicore.presentation.serializers import ser_document, ser_record

router = APIRouter(tags=["records"])


@router.get("/records", response_model=list[RecordResponse])
def list_records(
    actor: Actor,
    uow: UoW,
    patient_id: str | None = Query(None),
    type: str | None = Query(None),
):
    with uow:
        f = RecordFilter(patient_id=patient_id, type=type) if (patient_id or type) else None
        records = ListMedicalRecords(uow).execute(actor, f)
        # Resolve patient names with per-id caching (mirrors _ser_appointments).
        names: dict = {}
        for r in records:
            if r.patient_id not in names:
                p = uow.patients.get_by_id(r.patient_id)
                names[r.patient_id] = p.full_name if p else None
        return [ser_record(r, patient_name=names[r.patient_id]) for r in records]


@router.get("/records/{record_id}", response_model=RecordResponse)
def get_record(record_id: str, actor: Actor, uow: UoW, clock: Clock):
    record = GetMedicalRecord(uow, clock).execute(actor, RecordId.parse(record_id))
    return ser_record(record)


@router.post("/records/{record_id}/amend", response_model=RecordResponse)
def amend_record(record_id: str, body: AmendRequest, actor: Actor, uow: UoW, clock: Clock):
    changes: dict = {}
    if body.chief_complaint is not None:
        changes["chief_complaint"] = body.chief_complaint
    if body.soap is not None:
        changes["soap"] = SoapNote(**body.soap)
    amendment = AmendMedicalRecord(uow, clock).execute(actor, RecordId.parse(record_id), **changes)
    return ser_record(amendment)


@router.post("/documents", response_model=DocumentResponse, status_code=201)
def upload_document(body: UploadDocumentRequest, actor: Actor, uow: UoW, clock: Clock):
    cmd = UploadDocumentCommand(
        patient_id=PatientId.parse(body.patient_id),
        file_name=body.file_name,
        kind=DocumentKind(body.kind),
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        storage_key=body.storage_key,
        record_id=RecordId.parse(body.record_id) if body.record_id else None,
    )
    doc = UploadDocument(uow, clock).execute(actor, cmd)
    return ser_document(doc)


@router.get("/patients/{patient_id}/documents", response_model=list[DocumentResponse])
def list_documents(patient_id: str, actor: Actor, uow: UoW):
    with uow:
        docs = ListPatientDocuments(uow).execute(actor, PatientId.parse(patient_id))
    return [ser_document(d) for d in docs]
