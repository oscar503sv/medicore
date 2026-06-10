"""ORM models for DoctorAvailability and AvailabilityException."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class DoctorAvailabilityModel(Base):
    __tablename__ = "doctor_availability"
    __table_args__ = (
        UniqueConstraint("tenant_id", "doctor_id", name="uq_availability_tenant_doctor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # weekly: list of {day_of_week, enabled, blocks:[{start,end}]}
    weekly: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # rules: {slot_minutes, min_advance_hours, allow_same_day} — legacy keys in stored JSON
    # (buffer_minutes, max_advance_days) are ignored by the mapper.
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AvailabilityExceptionModel(Base):
    __tablename__ = "availability_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    availability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("doctor_availability.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # blocks: list of {start, end} (only for 'extra' kind)
    blocks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
