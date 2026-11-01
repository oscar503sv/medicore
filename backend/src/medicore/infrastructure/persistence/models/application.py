"""ORM models for in-clinic medication applications: orders and the records of each dose."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class ApplicationOrderModel(Base):
    __tablename__ = "application_orders"
    __table_args__ = (
        Index("ix_application_orders_patient", "tenant_id", "patient_id"),
        # The worklist reads the open orders.
        Index("ix_application_orders_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    drug: Mapped[str] = mapped_column(String(120), nullable=False)
    dose: Mapped[str] = mapped_column(String(60), nullable=False)
    route: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    doses_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observation_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    instructions: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ordered_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    external_prescriber: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_jvpm: Mapped[str | None] = mapped_column(String(10), nullable=True)
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)


class ApplicationRecordModel(Base):
    __tablename__ = "application_records"
    __table_args__ = (
        Index("ix_application_records_order", "tenant_id", "order_id"),
        Index("ix_application_records_time", "tenant_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    dose_number: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lot: Mapped[str | None] = mapped_column(String(60), nullable=True)
    lot_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    site: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_pressure: Mapped[str | None] = mapped_column(String(10), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    allergy_override: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    observe_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation_closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observation_closed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reaction: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reaction_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
