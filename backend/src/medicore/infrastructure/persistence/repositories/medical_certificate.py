"""SQLAlchemy MedicalCertificateRepository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.enums import CertificateKind
from medicore.domain.shared.identifiers import (
    CertificateId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.infrastructure.persistence.models.medical_certificate import (
    MedicalCertificateModel,
)


def _to_entity(row: MedicalCertificateModel) -> MedicalCertificate:
    return MedicalCertificate(
        id=CertificateId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        code=row.code,
        patient_id=PatientId.parse(row.patient_id),
        record_id=RecordId.parse(row.record_id),
        doctor_id=UserId.parse(row.doctor_id),
        kind=CertificateKind(row.kind),
        issued_at=row.issued_at,
        rest_from=row.rest_from,
        rest_days=row.rest_days,
        diagnosis=row.diagnosis,
        remarks=row.remarks,
        addressee=row.addressee,
        voided_at=row.voided_at,
        voided_by_id=UserId.parse(row.voided_by_id) if row.voided_by_id else None,
        void_reason=row.void_reason,
        created_at=row.created_at,
    )


class SqlMedicalCertificateRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(MedicalCertificateModel).filter(
            MedicalCertificateModel.tenant_id == self._tid
        )

    def get_by_id(self, certificate_id: CertificateId) -> MedicalCertificate | None:
        row = self._q().filter(MedicalCertificateModel.id == certificate_id.value).first()
        return _to_entity(row) if row else None

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalCertificate]:
        rows = self._q().filter(MedicalCertificateModel.patient_id == patient_id.value)
        return [_to_entity(r) for r in rows.order_by(MedicalCertificateModel.issued_at.desc())]

    def list_by_record(self, record_id: RecordId) -> list[MedicalCertificate]:
        rows = self._q().filter(MedicalCertificateModel.record_id == record_id.value)
        return [_to_entity(r) for r in rows.order_by(MedicalCertificateModel.issued_at.desc())]

    def save(self, certificate: MedicalCertificate) -> None:
        row = self._s.get(MedicalCertificateModel, certificate.id.value)
        if row is None:
            row = MedicalCertificateModel(id=certificate.id.value)
            self._s.add(row)
        c = certificate
        row.tenant_id = c.tenant_id.value
        row.code = c.code
        row.patient_id = c.patient_id.value
        row.record_id = c.record_id.value
        row.doctor_id = c.doctor_id.value
        row.kind = str(c.kind)
        row.issued_at = c.issued_at
        row.rest_from = c.rest_from
        row.rest_days = c.rest_days
        row.diagnosis = c.diagnosis
        row.remarks = c.remarks
        row.addressee = c.addressee
        row.voided_at = c.voided_at
        row.voided_by_id = c.voided_by_id.value if c.voided_by_id else None
        row.void_reason = c.void_reason
        row.created_at = c.created_at
