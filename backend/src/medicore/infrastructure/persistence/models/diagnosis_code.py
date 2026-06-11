"""ORM model for the global ICD/CIE diagnosis catalog (not tenant-scoped)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class DiagnosisCodeModel(Base):
    __tablename__ = "diagnosis_codes"
    __table_args__ = (
        UniqueConstraint("version", "code", name="uq_diagnosis_version_code"),
        # Trigram index for fast substring/typo search over code + label.
        Index(
            "ix_diagnosis_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        # text_pattern_ops serves the LIKE 'E11%' code-prefix branch of the search.
        Index(
            "ix_diagnosis_version_code",
            "version",
            "code",
            postgresql_ops={"code": "text_pattern_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    search_text: Mapped[str] = mapped_column(String(600), nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    chapter: Mapped[str | None] = mapped_column(String(255), nullable=True)
