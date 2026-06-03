"""SQLAlchemy repository for the global ICD/CIE diagnosis catalog (not tenant-scoped)."""

from __future__ import annotations

import unicodedata

from sqlalchemy import or_
from sqlalchemy.orm import Session

from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis
from medicore.infrastructure.persistence.models.diagnosis_code import DiagnosisCodeModel


def normalize_search(text: str) -> str:
    """Lowercase + strip accents so 'Migraña' and 'migrana' both match."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def build_search_text(code: str, label: str) -> str:
    return normalize_search(f"{code} {label}")


class SqlDiagnosisCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def search(self, version: str, query: str, limit: int = 20) -> list[CatalogDiagnosis]:
        q = (query or "").strip()
        if not q:
            return []
        norm = normalize_search(q)
        code_prefix = q.upper()
        rows = (
            self._s.query(DiagnosisCodeModel)
            .filter(DiagnosisCodeModel.version == version)
            .filter(
                or_(
                    DiagnosisCodeModel.code.ilike(f"{code_prefix}%"),
                    DiagnosisCodeModel.search_text.ilike(f"%{norm}%"),
                )
            )
            .order_by(DiagnosisCodeModel.code)
            .limit(limit)
            .all()
        )
        return [
            CatalogDiagnosis(
                version=r.version, code=r.code, label=r.label, billable=r.billable,
                chapter=r.chapter,
            )
            for r in rows
        ]

    def count(self, version: str) -> int:
        return (
            self._s.query(DiagnosisCodeModel)
            .filter(DiagnosisCodeModel.version == version)
            .count()
        )

    def upsert(self, entry: CatalogDiagnosis) -> None:
        row = (
            self._s.query(DiagnosisCodeModel)
            .filter(
                DiagnosisCodeModel.version == entry.version,
                DiagnosisCodeModel.code == entry.code,
            )
            .first()
        )
        if row is None:
            row = DiagnosisCodeModel(version=entry.version, code=entry.code)
            self._s.add(row)
        row.label = entry.label
        row.search_text = build_search_text(entry.code, entry.label)
        row.billable = entry.billable
        row.chapter = entry.chapter
