"""ORM model for Appointment."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class AppointmentModel(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_tenant_day", "tenant_id", "scheduled_start"),
        Index("ix_appointments_doctor_day", "doctor_id", "scheduled_start"),
        Index("ix_appointments_agenda_day", "agenda_id", "scheduled_start"),
        # Lets other tables point at an appointment together with its clinic (composite FK).
        UniqueConstraint("tenant_id", "id", name="uq_appointments_tenant_id"),
        # The agenda must belong to the appointment's clinic.
        ForeignKeyConstraint(
            ["tenant_id", "agenda_id"], ["service_agendas.tenant_id", "service_agendas.id"],
            name="fk_appointments_tenant_agenda",
        ),
        # Attended by a doctor or by a service agenda, never both and never neither.
        CheckConstraint(
            "num_nonnulls(doctor_id, agenda_id) = 1", name="ck_appointments_one_assignee"
        ),
        # A vaccination visit is charged at most what its private doses add up to.
        CheckConstraint(
            "type <> 'vaccination' OR listed_fee IS NULL OR fee <= listed_fee",
            name="ck_appointments_vaccination_fee_cap",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    agenda_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")
    insurance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insurers.id"), nullable=True
    )
    # Stored as a naive wall-clock in the clinic's timezone (the slot resolver works in local
    # wall-clock). Kept tz-naive so it round-trips without a spurious UTC offset on read.
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    room: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Fee (USD): the doctor's price when booked, what is charged, and why they differ.
    listed_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_walk_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Vitals taken before the consultation starts (see Appointment.pre_vitals); never serialized
    # with the appointment.
    pre_vitals: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    pre_vitals_saved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
