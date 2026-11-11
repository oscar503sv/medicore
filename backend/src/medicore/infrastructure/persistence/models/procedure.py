"""ORM models for minor procedures: the clinic's catalog and each procedure done."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class ProcedureTypeModel(Base):
    __tablename__ = "procedure_types"
    __table_args__ = (Index("ix_procedure_types_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    performer: Mapped[str] = mapped_column(String(20), nullable=False)
    requires_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    follow_up_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    takes_specimen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    technique_template: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    instructions_template: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)  # USD


class ProcedureModel(Base):
    __tablename__ = "procedures"
    __table_args__ = (
        Index("ix_procedures_patient", "tenant_id", "patient_id"),
        # The worklist reads the open ones and the recently signed ones.
        Index("ix_procedures_status", "tenant_id", "status"),
        Index("ix_procedures_performed", "tenant_id", "performed_at"),
        Index("ix_procedures_appointment", "tenant_id", "appointment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procedure_types.id", ondelete="RESTRICT"), nullable=False
    )
    type_name: Mapped[str] = mapped_column(String(120), nullable=False)
    performer: Mapped[str] = mapped_column(String(20), nullable=False)
    requires_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    indication: Mapped[str] = mapped_column(String(500), nullable=False)
    ordered_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    follow_up_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    takes_specimen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    allergies_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anticoagulants: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fasting: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    allergy_override: Mapped[str | None] = mapped_column(String(300), nullable=True)
    consent_signer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consent_relationship: Mapped[str | None] = mapped_column(String(60), nullable=True)
    consent_witness: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    bp_before: Mapped[str | None] = mapped_column(String(10), nullable=True)
    hr_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spo2_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temp_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    bp_after: Mapped[str | None] = mapped_column(String(10), nullable=True)
    hr_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spo2_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temp_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    anesthesia: Mapped[str | None] = mapped_column(String(300), nullable=True)
    technique: Mapped[str | None] = mapped_column(String(3000), nullable=True)
    findings: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    materials: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    complications: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    instructions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    specimen_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    specimen_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    performed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amendments: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # fee (USD): the catalog price when ordered, what is charged, and why they differ
    listed_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fee_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
