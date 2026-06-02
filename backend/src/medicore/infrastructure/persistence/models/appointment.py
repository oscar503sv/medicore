"""ORM model for Appointment."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class AppointmentModel(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_tenant_day", "tenant_id", "scheduled_start"),
        Index("ix_appointments_doctor_day", "doctor_id", "scheduled_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")
    insurance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insurers.id"), nullable=True
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    room: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
