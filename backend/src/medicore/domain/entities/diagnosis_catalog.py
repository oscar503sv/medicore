"""Catalog diagnosis — a reference ICD/CIE code+label, shared across all tenants.

This is reference data (not a tenant aggregate): the WHO CIE-10 / CIE-11 catalogs are imported
into a global table and queried for the diagnosis autocomplete in the live consultation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CatalogDiagnosis:
    version: str  # IcdVersion value: "cie10" | "cie11"
    code: str
    label: str
    billable: bool = True
    chapter: str | None = None
