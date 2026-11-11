"""Medical certificate use cases: issue a constancia from a signed record, list, void.

Only the doctor who signed the visit issues (and voids) its certificates: the paper carries
their name, JVPM and signature. Whoever can read records can list and reprint them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.ports.clock import Clock
from medicore.application.ports.code_generator import CodeGenerator
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import CertificateKind
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import CertificateId, PatientId, RecordId


@dataclass(frozen=True, slots=True)
class IssueCertificateCommand:
    record_id: RecordId
    kind: CertificateKind
    rest_from: date | None = None
    rest_days: int | None = None
    include_diagnosis: bool = False
    remarks: str | None = None
    addressee: str | None = None


def diagnosis_text(record: MedicalRecord) -> str | None:
    """The record's diagnoses as they are printed: "J06.9 Infección aguda…; N76.0 …"."""
    if not record.diagnoses:
        return None
    return "; ".join(f"{d.code} {d.label}".strip() for d in record.diagnoses)


class IssueMedicalCertificate:
    def __init__(self, uow: UnitOfWork, codes: CodeGenerator, clock: Clock) -> None:
        self._uow = uow
        self._codes = codes
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: IssueCertificateCommand) -> MedicalCertificate:
        ensure_permission(actor, Permission.RECORDS_SIGN)
        record = self._uow.medical_records.get_by_id(cmd.record_id)
        if record is None:
            raise EntityNotFound("MedicalRecord", cmd.record_id)
        if record.author_id != actor.user_id:
            raise PermissionDenied(
                "only the doctor who signed the visit issues its certificates",
                code="certificate.not_own",
            )
        patient = self._uow.patients.get_by_id(record.patient_id)
        now = self._clock.now()
        certificate = MedicalCertificate(
            id=CertificateId.new(),
            tenant_id=actor.tenant_id,
            code=self._codes.next_certificate_code(now.date()),
            patient_id=record.patient_id,
            record_id=record.id,
            doctor_id=actor.user_id,
            kind=cmd.kind,
            issued_at=now,
            rest_from=cmd.rest_from,
            rest_days=cmd.rest_days,
            diagnosis=diagnosis_text(record) if cmd.include_diagnosis else None,
            remarks=cmd.remarks,
            addressee=cmd.addressee,
            created_at=now,
        )
        with self._uow:
            self._uow.certificates.save(certificate)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "certificate.issued", "MedicalCertificate", str(certificate.id),
                    kind=str(certificate.kind), record_id=str(record.id),
                    rest_days=certificate.rest_days,
                    diagnosis_disclosed=certificate.diagnosis is not None,
                    subject=subject(certificate.code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()
        return certificate


class ListMedicalCertificates:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, *, patient_id: PatientId | None = None,
        record_id: RecordId | None = None,
    ) -> list[MedicalCertificate]:
        ensure_permission(actor, Permission.RECORDS_VIEW)
        if record_id is not None:
            return self._uow.certificates.list_by_record(record_id)
        if patient_id is not None:
            return self._uow.certificates.list_by_patient(patient_id)
        return []


class VoidMedicalCertificate:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, certificate_id: CertificateId, reason: str
    ) -> MedicalCertificate:
        ensure_permission(actor, Permission.RECORDS_SIGN)
        certificate = self._uow.certificates.get_by_id(certificate_id)
        if certificate is None:
            raise EntityNotFound("MedicalCertificate", certificate_id)
        if certificate.doctor_id != actor.user_id:
            raise PermissionDenied(
                "only the doctor who issued the certificate voids it", code="certificate.not_own"
            )
        patient = self._uow.patients.get_by_id(certificate.patient_id)
        now = self._clock.now()
        with self._uow:
            certificate.void(actor.user_id, reason, now)
            self._uow.certificates.save(certificate)
            self._uow.audit.append(
                audit_entry(
                    actor, now, "certificate.voided", "MedicalCertificate", str(certificate.id),
                    reason=certificate.void_reason,
                    subject=subject(certificate.code, patient.full_name if patient else None),
                )
            )
            self._uow.commit()
        return certificate
