"""ORM model for Patient."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class PatientModel(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_patients_tenant_code"),
        Index("ix_patients_tenant_name", "tenant_id", "last_name", "first_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sex: Mapped[str] = mapped_column(String(10), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    blood_type: Mapped[str | None] = mapped_column(String(5), nullable=True)
    primary_doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    allergies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    contact: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
