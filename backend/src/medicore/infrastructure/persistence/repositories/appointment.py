"""SQLAlchemy AppointmentRepository."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import Date as SqlDate
from sqlalchemy import cast
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
        row.created_by_id = appointment.created_by_id.value
        row.created_at = appointment.created_at
        row.updated_at = appointment.updated_at
