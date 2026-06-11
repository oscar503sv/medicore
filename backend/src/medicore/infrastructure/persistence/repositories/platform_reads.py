"""Cross-tenant read model for the superadmin console (stats + global audit).

Uses a single global session and ``GROUP BY tenant_id`` aggregates over the shared physical
database — far cheaper than opening one UnitOfWork per tenant.
"""

from __future__ import annotations

from sqlalchemy import desc, func, literal, select, union_all
from sqlalchemy.orm import Session

from medicore.domain.repositories._support import GlobalAuditRow, Page
from medicore.domain.shared.identifiers import TenantId
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.audit_log import AuditLogModel
from medicore.infrastructure.persistence.models.consultation import ConsultationModel
from medicore.infrastructure.persistence.models.medical_record import MedicalRecordModel
from medicore.infrastructure.persistence.models.patient import PatientModel
from medicore.infrastructure.persistence.models.platform import (
    PlatformAdminModel,
    PlatformAuditLogModel,
)
from medicore.infrastructure.persistence.models.tenant import TenantModel
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
        category: str | None = None,
    ) -> Page[GlobalAuditRow]:
        """Consolidated, chronological view over both the tenant and platform audit trails."""

        def leg(model, kind: str):
            s = select(
                model.id.label("id"),
                model.actor_id.label("actor_id"),
                model.action.label("action"),
                model.metadata_.label("metadata"),
                model.timestamp.label("timestamp"),
                model.tenant_id.label("tenant_id"),
                model.ip_address.label("ip_address"),
                model.user_agent.label("user_agent"),
                literal(kind).label("source_kind"),
            )
            if category:
                # autoescape neutralizes LIKE wildcards in the user-provided category.
                s = s.where(model.action.startswith(f"{category}.", autoescape=True))
            return s

        u = union_all(
            leg(AuditLogModel, "tenant"), leg(PlatformAuditLogModel, "platform")
        ).subquery()
        total = self._s.execute(select(func.count()).select_from(u)).scalar_one()
        rows = self._s.execute(
            select(u).order_by(desc(u.c.timestamp)).offset(offset).limit(limit)
        ).all()

        # Resolve names in one round-trip each: tenant actors → users, platform actors → admins.
        tenant_actor_ids = {r.actor_id for r in rows if r.source_kind == "tenant"}
        platform_actor_ids = {r.actor_id for r in rows if r.source_kind == "platform"}
        clinic_ids = {r.tenant_id for r in rows if r.tenant_id is not None}
        user_names = (
            dict(
                self._s.query(UserModel.id, UserModel.name).filter(
                    UserModel.id.in_(tenant_actor_ids)
                )
            )
            if tenant_actor_ids
            else {}
        )
        admin_names = (
            dict(
                self._s.query(PlatformAdminModel.id, PlatformAdminModel.name).filter(
                    PlatformAdminModel.id.in_(platform_actor_ids)
                )
            )
            if platform_actor_ids
            else {}
        )
        clinic_names = (
            dict(
                self._s.query(TenantModel.id, TenantModel.legal_name).filter(
                    TenantModel.id.in_(clinic_ids)
                )
            )
            if clinic_ids
            else {}
        )

        items = [
            GlobalAuditRow(
                id=str(r.id),
                timestamp=r.timestamp,
                source_kind=r.source_kind,
                actor_name=(
                    user_names.get(r.actor_id)
                    if r.source_kind == "tenant"
                    else admin_names.get(r.actor_id)
                ),
                action=r.action,
                clinic_name=clinic_names.get(r.tenant_id) if r.tenant_id else None,
                metadata=dict(r.metadata or {}),
                ip_address=r.ip_address,
                user_agent=r.user_agent,
            )
            for r in rows
        ]
        return Page(items=items, total=total, offset=offset, limit=limit)
