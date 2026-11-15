"""Medical record and document use cases."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.notifications import DOCUMENT_UPLOADED, notify, treating_doctor
from medicore.application.common.permissions import (
    Permission,
    ensure_not_support,
    ensure_permission,
)
from medicore.application.common.timezone import clinic_instant
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import ClinicalRecordType, DocumentKind
from medicore.domain.repositories._support import Page, Paging, RecordFilter, RecordSummary
from medicore.domain.shared.errors import PermissionDenied, RecordSuperseded
from medicore.domain.shared.identifiers import (
    DocumentId,
    PatientId,
    RecordId,
    UserId,
)
from medicore.domain.value_objects.vitals import Vitals

MAX_RECORDS_PAGE = 100
MAX_SEARCH_LENGTH = 100


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    patient_id: PatientId
    file_name: str
    kind: DocumentKind
    mime_type: str
    size_bytes: int
    storage_key: str
    record_id: RecordId | None = None


@dataclass(frozen=True, slots=True)
class RecordQuery:
    patient_id: PatientId | None = None
    type: ClinicalRecordType | None = None
    date_from: date | None = None  # clinic days, inclusive
    date_to: date | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True)
class VitalsReading:
    record_id: RecordId
    record_code: str
    encounter_at: datetime
    vitals: Vitals


@dataclass(frozen=True, slots=True)
class RecordView:
    """A record and, when it was amended, the version that replaced it."""

    record: MedicalRecord
    superseded_by_id: RecordId | None


@dataclass(frozen=True, slots=True)
class RecordVersion:
    record: MedicalRecord
    version: int  # 1 is the original
    signer_name: str | None
    is_current: bool


def summarize(
    record: MedicalRecord, patient_name: str | None, signer_name: str | None
) -> RecordSummary:
    return RecordSummary(
        id=str(record.id),
        code=record.code,
        patient_id=str(record.patient_id),
        patient_name=patient_name,
        type=str(record.type),
        status=str(record.status),
        encounter_at=record.encounter_at,
        location_name=record.location_name,
        signed_by_id=str(record.signed_by_id),
        signed_by_name=signer_name,
        consultation_id=str(record.consultation_id) if record.consultation_id else None,
        amends_record_id=str(record.amends_record_id) if record.amends_record_id else None,
    )


def vitals_readings(records: list[MedicalRecord]) -> list[VitalsReading]:
    """The records that captured vitals, in the order given (newest first)."""
    return [
        VitalsReading(r.id, r.code, r.encounter_at, r.vitals)
        for r in records
        if not r.vitals.is_empty()
    ]


class ListMedicalRecords:
    """The records list as anyone with records.view sees it: metadata only (see
    ``RecordSummary``), paginated and audited."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _instant(self, actor: ActorContext, day: date) -> datetime:
        return clinic_instant(
            self._uow, actor.tenant_id, self._clock, datetime.combine(day, time.min)
        )

    def execute(
        self, actor: ActorContext, query: RecordQuery, paging: Paging
    ) -> Page[RecordSummary]:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        if query.date_from and query.date_to and query.date_from > query.date_to:
            raise ValidationError("date_from is after date_to", code="records.invalid_range")
        paging = Paging(offset=paging.offset, limit=min(paging.limit, MAX_RECORDS_PAGE))
        search = (query.search or "").strip()[:MAX_SEARCH_LENGTH] or None
        record_filter = RecordFilter(
            patient_id=str(query.patient_id) if query.patient_id else None,
            type=str(query.type) if query.type else None,
            encounter_from=self._instant(actor, query.date_from) if query.date_from else None,
            encounter_before=(
                self._instant(actor, query.date_to + timedelta(days=1)) if query.date_to else None
            ),
            search=search,
        )
        page = self._uow.medical_records.summaries(record_filter, paging)
        patient = self._uow.patients.get_by_id(query.patient_id) if query.patient_id else None
        # Listing who was seen, when and by whom is itself access to clinical data. The
        # search text is never stored: it is often a patient's name.
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "record.listed",
                    "Patient" if query.patient_id else "MedicalRecord",
                    str(query.patient_id) if query.patient_id else "list",
                    patient_id=str(query.patient_id) if query.patient_id else None,
                    type=str(query.type) if query.type else None,
                    date_from=query.date_from.isoformat() if query.date_from else None,
                    date_to=query.date_to.isoformat() if query.date_to else None,
                    searched=search is not None,
                    offset=page.offset,
                    returned=len(page.items),
                    total=page.total,
                    subject=subject(patient.code, patient.full_name) if patient else None,
                )
            )
            self._uow.commit()
        return page


class GetMedicalRecord:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, record_id: RecordId) -> RecordView:
        ensure_permission(actor, Permission.RECORDS_READ_CLINICAL)
        record = self._uow.medical_records.get_by_id(record_id)
        if record is None:
            raise EntityNotFound("MedicalRecord", record_id)
        superseded_by_id = self._uow.medical_records.successor_id(record_id)
        # Accessing patient clinical data is auditable (HIPAA/GDPR).
        patient = self._uow.patients.get_by_id(record.patient_id)
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "record.viewed", "MedicalRecord", str(record_id),
                    subject=subject(record.code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()
        return RecordView(record, superseded_by_id)


class ListRecordVersions:
    """Every version of a record, oldest first, for whoever may read its content."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, record_id: RecordId) -> list[RecordVersion]:
        ensure_permission(actor, Permission.RECORDS_READ_CLINICAL)
        chain = self._uow.medical_records.versions(record_id)
        if not chain:
            raise EntityNotFound("MedicalRecord", record_id)
        current = chain[-1]
        names: dict[UserId, str | None] = {}
        for r in chain:
            if r.signed_by_id not in names:
                signer = self._uow.users.get_by_id(r.signed_by_id)
                names[r.signed_by_id] = signer.name if signer else None
        patient = self._uow.patients.get_by_id(current.patient_id)
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "record.versions_viewed", "MedicalRecord",
                    str(current.id), count=len(chain),
                    subject=subject(current.code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()
        return [
            RecordVersion(r, number, names[r.signed_by_id], r is current)
            for number, r in enumerate(chain, start=1)
        ]


class _PatientRecordsReader:
    """Reads a patient's records and audits the access with how many were returned."""

    permission: Permission
    action: str

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _read[T](
        self, actor: ActorContext, patient_id: PatientId,
        shape: Callable[[list[MedicalRecord]], list[T]],
    ) -> list[T]:
        ensure_permission(actor, self.permission)
        patient = self._uow.patients.get_by_id(patient_id)
        if patient is None:
            raise EntityNotFound("Patient", patient_id)
        items = shape(self._uow.medical_records.list_by_patient(patient_id))
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), self.action, "Patient", str(patient_id),
                    count=len(items), subject=subject(patient.code, patient.full_name),
                )
            )
            self._uow.commit()
        return items


class ListPatientHistory(_PatientRecordsReader):
    """The patient's full clinical history: content, so doctors only."""

    permission = Permission.RECORDS_READ_CLINICAL
    action = "record.history_viewed"

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[MedicalRecord]:
        return self._read(actor, patient_id, list)


class ListPatientVitals(_PatientRecordsReader):
    """The vitals of the patient's visits, newest first (nothing else of the records)."""

    permission = Permission.RECORDS_VIEW
    action = "patient.vitals_listed"

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[VitalsReading]:
        return self._read(actor, patient_id, vitals_readings)


class AmendMedicalRecord:
    """Create a versioned amendment that references the original; never mutates it.

    Only the record's author amends it, only its current version, and always with a reason."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self,
        actor: ActorContext,
        record_id: RecordId,
        *,
        reason: str,
        chief_complaint: str | None = None,
        note: Mapping[str, str] | None = None,
    ) -> MedicalRecord:
        """``note`` rewrites sections of the note by key, in the template it was signed
        with."""
        ensure_permission(actor, Permission.RECORDS_AMEND)
        ensure_not_support(actor)
        with self._uow:
            # Locked: two amendments of the same version queue here and the second finds the
            # first one's version instead of branching the chain.
            original = self._uow.medical_records.get_for_update(record_id)
            if original is None:
                raise EntityNotFound("MedicalRecord", record_id)
            if original.author_id != actor.user_id:
                raise PermissionDenied(
                    "only the record's author may amend it", code="record.not_own"
                )
            if self._uow.medical_records.successor_id(original.id) is not None:
                current = self._uow.medical_records.versions(original.id)[-1]
                raise RecordSuperseded(
                    "the record has a newer version", current_id=str(current.id)
                )
            amendment = original.amend(
                by=actor.user_id,
                new_id=RecordId.new(),
                signed_at=self._clock.now(),
                reason=reason,
                chief_complaint=chief_complaint,
                note=original.note.with_texts(dict(note)) if note else None,
            )
            patient = self._uow.patients.get_by_id(original.patient_id)
            changed = ["chief_complaint"] if (
                amendment.chief_complaint != original.chief_complaint
            ) else []
            changed += [
                f"note.{a.key}"
                for a, b in zip(original.note.sections, amendment.note.sections, strict=True)
                if a.text.strip() != b.text.strip()
            ]
            self._uow.medical_records.save(amendment)
            # The reason's text stays in the record: the audit log is read by people who
            # may not read clinical content.
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "record.amended", "MedicalRecord",
                    str(amendment.id), amends=str(original.id), changed=changed,
                    reason_chars=len(amendment.amendment_reason or ""),
                    subject=subject(amendment.code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()
        return amendment


# Document metadata comes straight from the client; constrain it before persisting.
_ALLOWED_MIME_TYPES = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain"}
)
_MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
_STORAGE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
_FILE_NAME_FORBIDDEN = ("/", "\\", "..", "\x00")


def _validate_upload(cmd: UploadDocumentCommand) -> None:
    if cmd.mime_type not in _ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"unsupported mime type: {cmd.mime_type!r}",
            code="document.unsupported_type",
            mime_type=cmd.mime_type,
        )
    if cmd.size_bytes <= 0 or cmd.size_bytes > _MAX_DOCUMENT_BYTES:
        raise ValidationError(
            f"size_bytes must be between 1 and {_MAX_DOCUMENT_BYTES}",
            code="document.too_large",
            max_mb=_MAX_DOCUMENT_BYTES // (1024 * 1024),
        )
    name = cmd.file_name.strip()
    if not name or len(name) > 255 or any(seq in name for seq in _FILE_NAME_FORBIDDEN):
        raise ValidationError("invalid file name", code="document.invalid_name")
    if ".." in cmd.storage_key or not _STORAGE_KEY_RE.match(cmd.storage_key):
        raise ValidationError("invalid storage key", code="document.invalid_storage_key")


class UploadDocument:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: UploadDocumentCommand) -> MedicalDocument:
        ensure_permission(actor, Permission.RECORDS_UPLOAD)
        _validate_upload(cmd)
        patient = self._uow.patients.get_by_id(cmd.patient_id)
        if patient is None:
            raise EntityNotFound("Patient", cmd.patient_id)
        if cmd.record_id is not None and self._uow.medical_records.get_by_id(cmd.record_id) is None:
            raise EntityNotFound("MedicalRecord", cmd.record_id)
        document = MedicalDocument(
            id=DocumentId.new(),
            tenant_id=actor.tenant_id,
            patient_id=cmd.patient_id,
            file_name=cmd.file_name,
            kind=cmd.kind,
            mime_type=cmd.mime_type,
            size_bytes=cmd.size_bytes,
            storage_key=cmd.storage_key,
            uploaded_by_id=actor.user_id,
            uploaded_at=self._clock.now(),
            record_id=cmd.record_id,
        )
        with self._uow:
            self._uow.documents.save(document)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "document.uploaded", "MedicalDocument",
                    str(document.id), subject=subject(document.file_name),
                )
            )
            # The file name is deliberately left out: it often describes clinical content.
            notify(
                self._uow, actor, self._clock.now(), DOCUMENT_UPLOADED,
                [treating_doctor(self._uow, patient)],
                document_id=str(document.id),
                kind=str(document.kind),
                patient_id=str(document.patient_id),
                patient_name=patient.full_name,
            )
            self._uow.commit()
        return document


class ListPatientDocuments:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, patient_id: PatientId) -> list[MedicalDocument]:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        documents = self._uow.documents.list_by_patient(patient_id)
        patient = self._uow.patients.get_by_id(patient_id)
        with self._uow:
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "document.listed", "Patient", str(patient_id),
                    count=len(documents),
                    subject=subject(patient.code, patient.full_name) if patient else None,
                )
            )
            self._uow.commit()
        return documents
