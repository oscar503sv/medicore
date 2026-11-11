"""ORM model for Patient."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.domain.shared.text import ACCENTED, PLAIN
from medicore.infrastructure.database.base import Base


def patient_search_sql(table: str = "") -> dict[str, str]:
    """The normalized expressions the patient search matches against, as literal SQL.

    Shared by the trigram indexes below and by the search query: Postgres only uses an
    expression index when the query repeats the expression exactly, constants included,
    so these must not be rebuilt with bound parameters. ``table`` qualifies the columns
    for the query ("patients."); the index definitions leave them bare.
    """
    t = table
    return {
        # Accent- and case-folded full name (SQL twin of domain.shared.text.fold).
        "name": f"translate(lower({t}first_name || ' ' || {t}last_name), '{ACCENTED}', '{PLAIN}')",
        "code": f"lower({t}code)",
        # Digits only, so "7012-3456" and "70123456" match alike.
        "phone": f"regexp_replace(coalesce({t}contact ->> 'phone', ''), '[^0-9]', '', 'g')",
    }


def _trgm_index(key: str) -> Index:
    expr = patient_search_sql()[key]
    return Index(
        f"ix_patients_search_{key}_trgm", text(f"({expr}) gin_trgm_ops"), postgresql_using="gin"
    )


class PatientModel(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_patients_tenant_code"),
        Index("ix_patients_tenant_name", "tenant_id", "last_name", "first_name"),
        # Substring search (LIKE '%word%') over name, code and phone: trigram GIN indexes,
        # one per branch of the search's OR so Postgres can combine them (BitmapOr).
        _trgm_index("name"),
        _trgm_index("code"),
        _trgm_index("phone"),
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
