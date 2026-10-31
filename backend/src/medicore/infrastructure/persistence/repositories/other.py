"""SQLAlchemy repositories for Availability, Notification and AuditLog."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.notification import Notification
from medicore.domain.repositories._support import AuditFilter, Page, Paging
from medicore.domain.shared.identifiers import (
    NotificationId,
    TenantId,
    UserId,
)
from medicore.infrastructure.persistence.mappers.availability import (
    from_doctor_availability,
    to_doctor_availability,
)
from medicore.infrastructure.persistence.mappers.entities import to_audit_log, to_notification
from medicore.infrastructure.persistence.models.audit_log import AuditLogModel
from medicore.infrastructure.persistence.models.availability import (
    AvailabilityExceptionModel,
    DoctorAvailabilityModel,
)
from medicore.infrastructure.persistence.models.notification import NotificationModel


class SqlDoctorAvailabilityRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def get_by_doctor(self, doctor_id: UserId) -> DoctorAvailability | None:
        row = (
            self._s.query(DoctorAvailabilityModel)
            .filter(
                DoctorAvailabilityModel.tenant_id == self._tid,
                DoctorAvailabilityModel.doctor_id == doctor_id.value,
            )
            .first()
        )
        if row is None:
            return None
        exceptions = (
            self._s.query(AvailabilityExceptionModel)
            .filter(AvailabilityExceptionModel.availability_id == row.id)
            .all()
        )
        return to_doctor_availability(row, exceptions)

    def save(self, availability: DoctorAvailability) -> None:
        av_dict, ex_dicts = from_doctor_availability(availability)
        row = self._s.get(DoctorAvailabilityModel, availability.id.value)
        if row is None:
            row = DoctorAvailabilityModel(id=availability.id.value)
            self._s.add(row)
        row.tenant_id = av_dict["tenant_id"]
        row.doctor_id = av_dict["doctor_id"]
        row.weekly = av_dict["weekly"]
        row.rules = av_dict["rules"]

        # Replace exceptions entirely
        (
            self._s.query(AvailabilityExceptionModel)
            .filter(AvailabilityExceptionModel.availability_id == availability.id.value)
            .delete()
        )
        for ex_d in ex_dicts:
            ex_row = AvailabilityExceptionModel(
                id=ex_d["id"],
                availability_id=ex_d["availability_id"],
                date=ex_d["date"],
                kind=ex_d["kind"],
                reason=ex_d["reason"],
                blocks=ex_d["blocks"],
            )
            self._s.add(ex_row)


class SqlNotificationRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(NotificationModel).filter(NotificationModel.tenant_id == self._tid)

    def _mine(self, user_id: UserId):
        return self._q().filter(NotificationModel.user_id == user_id.value)

    def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        row = self._q().filter(NotificationModel.id == notification_id.value).first()
        return to_notification(row) if row else None

    def list_by_user(
        self,
        user_id: UserId,
        unread_only: bool = False,
        paging: Paging | None = None,
        category: str | None = None,
    ) -> list[Notification]:
        paging = paging or Paging()
        q = self._mine(user_id)
        if unread_only:
            q = q.filter(NotificationModel.read_at.is_(None))
        if category:
            q = q.filter(NotificationModel.type.startswith(f"{category}.", autoescape=True))
        rows = (
            q.order_by(NotificationModel.created_at.desc(), NotificationModel.id.desc())
            .offset(paging.offset)
            .limit(paging.limit)
            .all()
        )
        return [to_notification(r) for r in rows]

    def count_unread(self, user_id: UserId) -> int:
        return self._mine(user_id).filter(NotificationModel.read_at.is_(None)).count()

    def mark_all_read(self, user_id: UserId, when: datetime) -> int:
        return (
            self._mine(user_id)
            .filter(NotificationModel.read_at.is_(None))
            .update({NotificationModel.read_at: when}, synchronize_session=False)
        )

    def delete_read_before(self, user_id: UserId, cutoff: datetime) -> int:
        return (
            self._mine(user_id)
            .filter(NotificationModel.read_at.is_not(None), NotificationModel.read_at < cutoff)
            .delete(synchronize_session=False)
        )

    def save(self, notification: Notification) -> None:
        row = self._s.get(NotificationModel, notification.id.value)
        if row is None:
            row = NotificationModel(id=notification.id.value)
            self._s.add(row)
        row.tenant_id = notification.tenant_id.value
        row.user_id = notification.user_id.value
        row.type = notification.type
        row.data = dict(notification.data)
        row.read_at = notification.read_at
        row.created_at = notification.created_at


class SqlAuditLogRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(AuditLogModel).filter(AuditLogModel.tenant_id == self._tid)

    def append(self, entry: AuditLog) -> None:
        row = AuditLogModel(
            id=entry.id.value,
            tenant_id=entry.tenant_id.value,
            actor_id=entry.actor_id.value,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            metadata_=dict(entry.metadata),
            timestamp=entry.timestamp,
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
        )
        self._s.add(row)

    def query(self, **criteria: object) -> list[AuditLog]:
        q = self._q().order_by(AuditLogModel.timestamp)
        for key, value in criteria.items():
            if hasattr(AuditLogModel, key):
                q = q.filter(getattr(AuditLogModel, key) == value)
        return [to_audit_log(r) for r in q.all()]

    def list(
        self, filter: AuditFilter | None = None, paging: Paging | None = None
    ) -> Page[AuditLog]:
        from datetime import UTC, datetime, timedelta

        paging = paging or Paging()
        q = self._q()
        if filter:
            if filter.action:
                q = q.filter(AuditLogModel.action == filter.action)
            if filter.category:
                # autoescape neutralizes LIKE wildcards in the user-provided category;
                # without it, "%"/"_" would still act as wildcards.
                q = q.filter(
                    AuditLogModel.action.startswith(f"{filter.category}.", autoescape=True)
                )
            if filter.entity_type:
                q = q.filter(AuditLogModel.entity_type == filter.entity_type)
            if filter.actor_id:
                q = q.filter(AuditLogModel.actor_id == UserId.parse(filter.actor_id).value)
            if filter.date_from:
                start = datetime.fromisoformat(filter.date_from).replace(tzinfo=UTC)
                q = q.filter(AuditLogModel.timestamp >= start)
            if filter.date_to:
                end = datetime.fromisoformat(filter.date_to).replace(tzinfo=UTC) + timedelta(days=1)
                q = q.filter(AuditLogModel.timestamp < end)
        total = q.count()
        rows = (
            q.order_by(AuditLogModel.timestamp.desc())
            .offset(paging.offset)
            .limit(paging.limit)
            .all()
        )
        return Page(
            items=[to_audit_log(r) for r in rows],
            total=total,
            offset=paging.offset,
            limit=paging.limit,
        )
