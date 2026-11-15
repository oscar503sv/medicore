"""Medical records and documents router."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from medicore.application.use_cases.records import (
    MAX_RECORDS_PAGE,
    MAX_SEARCH_LENGTH,
    AmendMedicalRecord,
    GetMedicalRecord,
    ListMedicalRecords,
    ListPatientDocuments,
    ListPatientHistory,
    ListPatientVitals,
    ListRecordVersions,
    RecordQuery,
    UploadDocument,
    UploadDocumentCommand,
)
from medicore.domain.enums import ClinicalRecordType, SealStatus
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.identifiers import PatientId, RecordId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.records import (
    AmendRequest,
    DocumentResponse,
    RecordListResponse,
    RecordResponse,
    RecordVersionResponse,
    UploadDocumentRequest,
    VitalsReadingResponse,
)
from medicore.presentation.serializers import (
    ser_document,
    ser_record,
    ser_record_summary,
    ser_record_version,
    ser_vitals_reading,
)

router = APIRouter(tags=["records"])


@router.get("/records", response_model=RecordListResponse)
def list_records(
    actor: Actor,
    uow: UoW,
    clock: Clock,
    patient_id: str | None = Query(None),
    type: ClinicalRecordType | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    q: str | None = Query(None, max_length=MAX_SEARCH_LENGTH),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=MAX_RECORDS_PAGE),
):
    with uow:
        # Parse here so a malformed id is a 422, not a ValueError deep in the repository.
        query = RecordQuery(
            patient_id=PatientId.parse(patient_id) if patient_id else None,
            type=type, date_from=date_from, date_to=date_to, search=q,
        )
        page = ListMedicalRecords(uow, clock).execute(
            actor, query, Paging(offset=offset, limit=limit)
        )
    return RecordListResponse(
        items=[ser_record_summary(s) for s in page.items],
        total=page.total, offset=page.offset, limit=page.limit,
    )


@router.get("/records/{record_id}", response_model=RecordResponse)
def get_record(record_id: str, actor: Actor, uow: UoW, clock: Clock):
    view = GetMedicalRecord(uow, clock).execute(actor, RecordId.parse(record_id))
    record = view.record
    # Record who signed it (the doctor) for the document footer.
    signer = uow.users.get_by_id(record.signed_by_id)
    patient = uow.patients.get_by_id(record.patient_id)
    return ser_record(
        record,
        patient_name=patient.full_name if patient else None,
        signed_by_name=signer.name if signer else None,
        superseded_by_id=view.superseded_by_id,
        integrity=view.integrity,
    )


@router.get("/records/{record_id}/versions", response_model=list[RecordVersionResponse])
def list_record_versions(record_id: str, actor: Actor, uow: UoW, clock: Clock):
    with uow:
        versions = ListRecordVersions(uow, clock).execute(actor, RecordId.parse(record_id))
    return [ser_record_version(v) for v in versions]


@router.get("/patients/{patient_id}/records", response_model=list[RecordResponse])
def list_patient_history(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    pid = PatientId.parse(patient_id)
    with uow:
        records = ListPatientHistory(uow, clock).execute(actor, pid)
        patient = uow.patients.get_by_id(pid)
        patient_name = patient.full_name if patient else None
        names: dict = {}
        for r in records:
            if r.signed_by_id not in names:
                signer = uow.users.get_by_id(r.signed_by_id)
                names[r.signed_by_id] = signer.name if signer else None
        return [
            ser_record(r, patient_name=patient_name, signed_by_name=names[r.signed_by_id])
            for r in records
        ]


@router.get("/patients/{patient_id}/vitals", response_model=list[VitalsReadingResponse])
def list_patient_vitals(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    with uow:
        readings = ListPatientVitals(uow, clock).execute(actor, PatientId.parse(patient_id))
    return [ser_vitals_reading(v) for v in readings]


@router.post("/records/{record_id}/amend", response_model=RecordResponse)
def amend_record(record_id: str, body: AmendRequest, actor: Actor, uow: UoW, clock: Clock):
    amendment = AmendMedicalRecord(uow, clock).execute(
        actor, RecordId.parse(record_id),
        reason=body.reason, chief_complaint=body.chief_complaint, note=body.note,
    )
    return ser_record(amendment, integrity=SealStatus.OK)


@router.post("/documents", response_model=DocumentResponse, status_code=201)
def upload_document(body: UploadDocumentRequest, actor: Actor, uow: UoW, clock: Clock):
    cmd = UploadDocumentCommand(
        patient_id=PatientId.parse(body.patient_id),
        file_name=body.file_name,
        kind=body.kind,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        record_id=RecordId.parse(body.record_id) if body.record_id else None,
    )
    doc = UploadDocument(uow, clock).execute(actor, cmd)
    return ser_document(doc)


@router.get("/patients/{patient_id}/documents", response_model=list[DocumentResponse])
def list_documents(patient_id: str, actor: Actor, uow: UoW, clock: Clock):
    with uow:
        docs = ListPatientDocuments(uow, clock).execute(actor, PatientId.parse(patient_id))
    return [ser_document(d) for d in docs]
