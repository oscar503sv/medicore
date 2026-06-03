"""Import an ICD/CIE diagnosis catalog into the global ``diagnosis_codes`` table.

Two modes:

1. Seed a small built-in DEMO sample for both versions (offline, for development/demos):
       .venv/Scripts/python scripts/import_icd.py --sample

2. Import the full official catalog from a CSV with header ``code,label[,chapter,billable]``:
       .venv/Scripts/python scripts/import_icd.py cie11 data/cie11_mms.csv
       .venv/Scripts/python scripts/import_icd.py cie10 data/cie10.csv

   Official sources (download separately, place under backend/data/):
     - CIE-11 (MMS linearization): WHO ICD-11 browser → "Info / Download" (spreadsheet/API export)
       https://icd.who.int/ ; programmatic: https://id.who.int/ (ICD-API, OAuth client creds)
     - CIE-10: WHO ICD-10 tabular list / PAHO Spanish edition.

   The import is idempotent (upsert on version+code).
"""

from __future__ import annotations

import csv
import sys

from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis
from medicore.domain.enums import IcdVersion
from medicore.infrastructure.database.engine import get_session
from medicore.infrastructure.persistence.repositories.diagnosis_catalog import (
    SqlDiagnosisCatalogRepository,
)

# A tiny, representative sample so the autocomplete works end-to-end without the full files.
_SAMPLE: dict[str, list[tuple[str, str]]] = {
    "cie10": [
        ("I10", "Hipertensión esencial (primaria)"),
        ("E11.9", "Diabetes mellitus tipo 2 sin complicaciones"),
        ("J06.9", "Infección aguda de vías respiratorias superiores, no especificada"),
        ("F41.1", "Trastorno de ansiedad generalizada"),
        ("Z34.82", "Supervisión de embarazo normal, segundo trimestre"),
        ("G43.109", "Migraña con aura, no intratable"),
        ("M54.5", "Lumbago no especificado"),
        ("J45.909", "Asma no especificada, no complicada"),
        ("K21.9", "Enfermedad por reflujo gastroesofágico sin esofagitis"),
        ("N39.0", "Infección de vías urinarias, sitio no especificado"),
    ],
    "cie11": [
        ("BA00", "Hipertensión esencial"),
        ("5A11", "Diabetes mellitus tipo 2"),
        ("CA07.0", "Infección aguda de las vías respiratorias superiores"),
        ("6B00", "Trastorno de ansiedad generalizada"),
        ("QA40", "Supervisión de embarazo normal"),
        ("8A80.0", "Migraña con aura"),
        ("ME84.2", "Dolor lumbar bajo"),
        ("CA23", "Asma"),
        ("DA22", "Enfermedad por reflujo gastroesofágico"),
        ("GC08", "Infección del tracto urinario, sitio no especificado"),
    ],
}


def _seed_sample(repo: SqlDiagnosisCatalogRepository) -> int:
    n = 0
    for version, rows in _SAMPLE.items():
        for code, label in rows:
            repo.upsert(CatalogDiagnosis(version=version, code=code, label=label))
            n += 1
    return n


def _import_csv(repo: SqlDiagnosisCatalogRepository, version: str, path: str) -> int:
    IcdVersion(version)  # validate
    n = 0
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = (row.get("code") or "").strip()
            label = (row.get("label") or "").strip()
            if not code or not label:
                continue
            billable = (row.get("billable") or "true").strip().lower() not in ("false", "0", "no")
            repo.upsert(
                CatalogDiagnosis(
                    version=version, code=code, label=label,
                    billable=billable, chapter=(row.get("chapter") or None),
                )
            )
            n += 1
    return n


def main(argv: list[str]) -> None:
    session = get_session()
    try:
        repo = SqlDiagnosisCatalogRepository(session)
        if argv == ["--sample"]:
            n = _seed_sample(repo)
        elif len(argv) == 2:
            n = _import_csv(repo, argv[0], argv[1])
        else:
            raise SystemExit("usage: import_icd.py --sample | <version> <csv_path>")
        session.commit()
        print(f"imported {n} diagnosis codes")
    finally:
        session.close()


if __name__ == "__main__":
    main(sys.argv[1:])
