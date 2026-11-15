"""ORM model for MedicalRecord."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class MedicalRecordModel(Base):
    __tablename__ = "medical_records"
    __table_args__ = (
        Index("ix_records_tenant_patient", "tenant_id", "patient_id"),
        # The paginated records list is newest-first within a clinic.
        Index("ix_records_tenant_encounter", "tenant_id", "encounter_at"),
        # One original record per consultation (amendments repeat consultation_id): the
        # database backstop behind the sign lock.
        Index(
            "uq_medical_records_consultation",
            "consultation_id",
            unique=True,
            postgresql_where=text("consultation_id IS NOT NULL AND amends_record_id IS NULL"),
        ),
        # A record is amended at most once (the versions form a line); it also serves the
        # "is there a newer version" lookups.
        Index(
            "uq_medical_records_amends",
            "amends_record_id",
            unique=True,
            postgresql_where=text("amends_record_id IS NOT NULL"),
        ),
        CheckConstraint(
            "amends_record_id IS NULL OR amendment_reason IS NOT NULL",
            name="ck_medical_records_amendment_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="signed")
    encounter_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Insurer name frozen at sign time; NULL = self-pay ("Particular").
    insurer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chief_complaint: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    vitals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    diagnoses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    prescriptions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    vaccines: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    exams: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    attachments: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signed_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    amends_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medical_records.id"), nullable=True
    )
    amendment_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
