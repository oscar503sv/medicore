"""SQLAlchemy AppointmentRepository."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import Date as SqlDate
from sqlalchemy import cast, func
from sqlalchemy.orm import Session

from medicore.domain.entities.appointment import Appointment
from medicore.domain.enums import AppointmentStatus
from medicore.domain.shared.identifiers import AppointmentId, PatientId, TenantId, UserId
from medicore.infrastructure.persistence.mappers.entities import to_appointment
from medicore.infrastructure.persistence.models.appointment import AppointmentModel

_ACTIVE = {
    str(AppointmentStatus.SCHEDULED),
    str(AppointmentStatus.CONFIRMED),
    str(AppointmentStatus.IN_PROGRESS),
}


# Still to be attended: what the dashboard lists as "upcoming".
_PENDING = {str(AppointmentStatus.SCHEDULED), str(AppointmentStatus.CONFIRMED)}


def _naive(dt: datetime) -> datetime:
    """Drop tzinfo so naive (SQLite-stored) and aware (request) datetimes are comparable."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


class SqlAppointmentRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(AppointmentModel).filter(AppointmentModel.tenant_id == self._tid)

    def get_by_id(self, appointment_id: AppointmentId) -> Appointment | None:
        row = self._q().filter(AppointmentModel.id == appointment_id.value).first()
        return to_appointment(row) if row else None

    def list_by_day(self, on: date, doctor_id: UserId | None = None) -> list[Appointment]:
        q = (
            self._q()
            .filter(cast(AppointmentModel.scheduled_start, SqlDate) == on)
            .order_by(AppointmentModel.scheduled_start)
        )
        if doctor_id:
            q = q.filter(AppointmentModel.doctor_id == doctor_id.value)
        return [to_appointment(r) for r in q.all()]

    def list_by_patient(self, patient_id: PatientId) -> list[Appointment]:
        rows = (
            self._q()
            .filter(AppointmentModel.patient_id == patient_id.value)
            .order_by(AppointmentModel.scheduled_start)
            .all()
        )
        return [to_appointment(r) for r in rows]

    def last_visits(self, patient_ids: list[PatientId]) -> dict[PatientId, datetime]:
        if not patient_ids:
            return {}
        rows = (
            self._s.query(AppointmentModel.patient_id, func.max(AppointmentModel.scheduled_start))
            .filter(
                AppointmentModel.tenant_id == self._tid,
                AppointmentModel.patient_id.in_([pid.value for pid in patient_ids]),
                AppointmentModel.status == str(AppointmentStatus.COMPLETED),
            )
            .group_by(AppointmentModel.patient_id)
            .all()
        )
        return {PatientId.parse(pid): last for pid, last in rows}

    def exists_for_doctor(self, doctor_id: UserId) -> bool:
        return (
            self._q().filter(AppointmentModel.doctor_id == doctor_id.value).first() is not None
        )

    def count_patients_with_upcoming(self, now: datetime) -> int:
        return (
            self._q()
            .filter(
                AppointmentModel.status.in_(_ACTIVE),
                AppointmentModel.scheduled_start > _naive(now),
            )
            .with_entities(func.count(func.distinct(AppointmentModel.patient_id)))
            .scalar()
            or 0
        )

    def list_upcoming(
        self, after: datetime, limit: int, doctor_id: UserId | None = None
    ) -> list[Appointment]:
        q = self._q().filter(
            AppointmentModel.status.in_(_PENDING),
            AppointmentModel.scheduled_start >= _naive(after),
        )
        if doctor_id:
            q = q.filter(AppointmentModel.doctor_id == doctor_id.value)
        rows = (
            q.order_by(AppointmentModel.scheduled_start, AppointmentModel.code).limit(limit).all()
        )
        return [to_appointment(r) for r in rows]

    def next_visits(
        self, patient_ids: list[PatientId], now: datetime
    ) -> dict[PatientId, datetime]:
        if not patient_ids:
            return {}
        ids = [pid.value for pid in patient_ids]
        rows = (
            self._q()
            .filter(
                AppointmentModel.patient_id.in_(ids),
                AppointmentModel.status.in_(_ACTIVE),
            )
            .all()
        )
        # Stored datetimes may be naive (SQLite) while ``now`` is tz-aware; compare on a
        # single wall-clock reference by dropping tzinfo.
        cutoff = _naive(now)
        result: dict[PatientId, datetime] = {}
        for r in rows:
            if _naive(r.scheduled_start) <= cutoff:
                continue
            pid = PatientId.parse(r.patient_id)
            current = result.get(pid)
            if current is None or r.scheduled_start < current:
                result[pid] = r.scheduled_start
        return result

    def find_overlapping(
        self, doctor_id: UserId, start: datetime, end: datetime
    ) -> list[Appointment]:
        # Conservative 24-h window at DB level, then exact Python filter.
        rows = (
            self._q()
            .filter(
                AppointmentModel.doctor_id == doctor_id.value,
                AppointmentModel.status.in_(_ACTIVE),
                AppointmentModel.scheduled_start >= start - timedelta(hours=24),
                AppointmentModel.scheduled_start < end + timedelta(hours=24),
            )
            .all()
        )
        # Stored datetimes may be naive (SQLite) while request datetimes are tz-aware;
        # compare on a single wall-clock reference by dropping tzinfo.
        start, end = _naive(start), _naive(end)
        return [
            to_appointment(r)
            for r in rows
            if _naive(r.scheduled_start) < end
            and start < _naive(r.scheduled_start) + timedelta(minutes=r.duration_minutes)
        ]

    def save(self, appointment: Appointment) -> None:
        row = self._s.get(AppointmentModel, appointment.id.value)
        if row is None:
            row = AppointmentModel(id=appointment.id.value)
            self._s.add(row)
        row.tenant_id = appointment.tenant_id.value
        row.code = appointment.code
        row.patient_id = appointment.patient_id.value
        row.doctor_id = appointment.doctor_id.value
        row.location_id = appointment.location_id.value
        row.type = str(appointment.type)
        row.status = str(appointment.status)
        row.scheduled_start = appointment.scheduled_start
        row.duration_minutes = appointment.duration_minutes
        row.reason = appointment.reason
        row.room = appointment.room
        row.insurance_id = appointment.insurance_id.value if appointment.insurance_id else None
        row.created_by_id = appointment.created_by_id.value
        row.created_at = appointment.created_at
        row.updated_at = appointment.updated_at
