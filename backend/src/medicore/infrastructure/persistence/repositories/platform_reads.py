"""Cross-tenant read model for the superadmin console (stats + global audit).

Uses a single global session and ``GROUP BY tenant_id`` aggregates over the shared physical
database — far cheaper than opening one UnitOfWork per tenant.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.repositories._support import Page
from medicore.domain.shared.identifiers import TenantId
from medicore.infrastructure.persistence.mappers.entities import to_audit_log
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.audit_log import AuditLogModel
from medicore.infrastructure.persistence.models.consultation import ConsultationModel
from medicore.infrastructure.persistence.models.medical_record import MedicalRecordModel
from medicore.infrastructure.persistence.models.patient import PatientModel
from medicore.infrastructure.persistence.models.user import UserModel

_COUNTERS = {
    "patients": PatientModel,
    "users": UserModel,
    "appointments": AppointmentModel,
    "consultations": ConsultationModel,
    "records": MedicalRecordModel,
}


class SqlPlatformReadModel:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _grouped(self, model) -> dict[str, int]:
        rows = self._s.query(model.tenant_id, func.count()).group_by(model.tenant_id).all()
        return {str(tid): count for tid, count in rows}

    def counts_by_tenant(self) -> dict[str, dict[str, int]]:
        grouped = {name: self._grouped(model) for name, model in _COUNTERS.items()}
        result: dict[str, dict[str, int]] = {}
        for name, by_tenant in grouped.items():
            for tid, count in by_tenant.items():
                result.setdefault(tid, {})[name] = count
        return result

    def tenant_counts(self, tenant_id: TenantId) -> dict[str, int]:
        tid = tenant_id.value
        return {
            name: (
                self._s.query(func.count())
                .select_from(model)
                .filter(model.tenant_id == tid)
                .scalar()
                or 0
            )
            for name, model in _COUNTERS.items()
        }

    def global_audit(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        category: str | None = None,
        tenant_id: str | None = None,
    ) -> Page[AuditLog]:
        q = self._s.query(AuditLogModel)
        if action:
            q = q.filter(AuditLogModel.action == action)
        if category:
            q = q.filter(AuditLogModel.action.like(f"{category}.%"))
        if tenant_id:
            q = q.filter(AuditLogModel.tenant_id == tenant_id)
        total = q.count()
        rows = (
            q.order_by(AuditLogModel.timestamp.desc()).offset(offset).limit(limit).all()
        )
        return Page(
            items=[to_audit_log(r) for r in rows], total=total, offset=offset, limit=limit
        )
