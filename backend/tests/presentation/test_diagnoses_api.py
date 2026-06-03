"""API tests: diagnosis catalog endpoints."""

from __future__ import annotations

from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis


def _seed_catalog(seed):
    cat = seed.factory.diagnosis_catalog()
    cat.upsert(CatalogDiagnosis(version="cie11", code="BA00", label="Hipertensión esencial"))
    cat.upsert(CatalogDiagnosis(version="cie10", code="I10", label="Hipertensión esencial"))


def test_config_endpoint(seed, client, auth_headers):
    resp = client.get("/api/v1/diagnoses/config", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["version"] == "cie11"


def test_search_endpoint_uses_clinic_version(seed, client, auth_headers):
    _seed_catalog(seed)
    resp = client.get("/api/v1/diagnoses/search", params={"q": "hipert"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert [d["code"] for d in data] == ["BA00"]  # clinic default version is cie11


def test_search_requires_auth(client):
    assert client.get("/api/v1/diagnoses/search", params={"q": "x"}).status_code == 401
