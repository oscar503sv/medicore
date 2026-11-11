"""Cross-tenant read model for the superadmin console (business overview, clinic stats,
global audit).

Uses a single global session and ``GROUP BY tenant_id`` aggregates over the shared physical
database — far cheaper than opening one UnitOfWork per tenant.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import desc, func, literal, select, union_all
from sqlalchemy.orm import Session

from medicore.domain.repositories._support import (
    GlobalAuditRow,
    Page,
    PaymentSummary,
    TenantActivity,
)
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
from medicore.infrastructure.persistence.models.subscription import SubscriptionPaymentModel
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

    def tenant_counts(self, tenant_id: TenantId) -> dict[str, int]:
        """Totals of one clinic (clinic detail page)."""
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

    # ── Business overview ──────────────────────────────────────────────────────

    def active_staff_by_tenant(self) -> dict[str, dict[str, int]]:
        rows = (
            self._s.query(UserModel.tenant_id, UserModel.role, func.count())
            .filter(UserModel.status == "active")
            .group_by(UserModel.tenant_id, UserModel.role)
            .all()
        )
        out: dict[str, dict[str, int]] = {}
        for tid, role, count in rows:
            out.setdefault(str(tid), {})[str(role)] = count
        return out

    def payments_since(self, day: date) -> list[PaymentSummary]:
        rows = (
            self._s.query(
                SubscriptionPaymentModel.tenant_id,
                SubscriptionPaymentModel.amount,
                SubscriptionPaymentModel.paid_on,
            )
            .filter(SubscriptionPaymentModel.paid_on >= day)
            .all()
        )
        return [PaymentSummary(str(tid), amount, paid_on) for tid, amount, paid_on in rows]

    def activity_by_tenant(
        self, active_since: datetime, signed_since: datetime
    ) -> dict[str, TenantActivity]:
        last = dict(
            self._s.query(AuditLogModel.tenant_id, func.max(AuditLogModel.timestamp))
            .group_by(AuditLogModel.tenant_id)
            .all()
        )
        people = func.count(func.distinct(AuditLogModel.actor_id))
        active = dict(
            self._s.query(AuditLogModel.tenant_id, people)
            .filter(AuditLogModel.timestamp >= active_since)
            .group_by(AuditLogModel.tenant_id)
            .all()
        )
        signed = dict(
            self._s.query(MedicalRecordModel.tenant_id, func.count())
            .filter(MedicalRecordModel.signed_at >= signed_since)
            .group_by(MedicalRecordModel.tenant_id)
            .all()
        )
        return {
            str(tid): TenantActivity(
                last_activity=last.get(tid),
                active_users=active.get(tid, 0),
                signed_records=signed.get(tid, 0),
            )
            for tid in set(last) | set(active) | set(signed)
        }

    def signed_per_week(self, since: datetime) -> list[tuple[date, int]]:
        week = func.date_trunc("week", MedicalRecordModel.signed_at)
        rows = (
            self._s.query(week, func.count())
            .filter(MedicalRecordModel.signed_at >= since)
            .group_by(week)
            .order_by(week)
            .all()
        )
        return [(start.date(), count) for start, count in rows]

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
