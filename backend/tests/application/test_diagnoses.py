"""Tests for the diagnosis catalog search use cases."""

from __future__ import annotations

from medicore.application.use_cases.diagnoses import GetDiagnosisConfig, SearchDiagnoses
from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis
from medicore.domain.enums import IcdVersion
from tests.support.builders import seed_clinic


def _seed_catalog(seed):
    with seed.factory.diagnosis_catalog() as cat:
        cat.upsert(CatalogDiagnosis(version="cie10", code="I10", label="Hipertensión esencial"))
        cat.upsert(CatalogDiagnosis(version="cie10", code="F41.1", label="Ansiedad generalizada"))
        cat.upsert(CatalogDiagnosis(version="cie11", code="BA00", label="Hipertensión esencial"))


def test_config_defaults_to_cie11():
    seed = seed_clinic()
    assert GetDiagnosisConfig(seed.factory).execute(seed.doctor_actor) == "cie11"


def test_search_uses_clinic_version():
    seed = seed_clinic()
    _seed_catalog(seed)
    # clinic defaults to cie11 → only the cie11 entry matches
    results = SearchDiagnoses(seed.factory).execute(seed.doctor_actor, "hipertension")
    assert [r.code for r in results] == ["BA00"]


def test_search_matches_by_code_and_is_accent_insensitive():
    seed = seed_clinic()
    seed.tenant.icd_version = IcdVersion.CIE10
    seed.factory.store.tenants[seed.tenant.id.value] = seed.tenant
    _seed_catalog(seed)
    by_code = SearchDiagnoses(seed.factory).execute(seed.doctor_actor, "I10")
    assert by_code[0].code == "I10"
    by_label = SearchDiagnoses(seed.factory).execute(seed.doctor_actor, "Hipertension")
    assert any(r.code == "I10" for r in by_label)


def test_empty_query_returns_nothing():
    seed = seed_clinic()
    _seed_catalog(seed)
    assert SearchDiagnoses(seed.factory).execute(seed.doctor_actor, "") == []
