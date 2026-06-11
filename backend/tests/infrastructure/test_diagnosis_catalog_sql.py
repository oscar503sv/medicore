"""Integration tests: SqlDiagnosisCatalogRepository search against a real PostgreSQL.

The in-memory repository mirrors the ranking contract, but the trigram typo fallback
(word_similarity) and the LIKE-wildcard escaping only exist in SQL — these tests verify
them for real, plus the relevance ordering the autocomplete depends on.

They use TEST_DATABASE_URL (or DATABASE_URL from settings) and SKIP when PostgreSQL is
unreachable. Everything runs inside one outer transaction that is rolled back, so the
dev database (which may already hold the full imported catalog) is left untouched; the
tests seed synthetic versions ("t10"/"t11") so real catalog rows never match.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.repositories.diagnosis_catalog import (
    SqlDiagnosisCatalogRepository,
)


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("PostgreSQL not available")
    yield engine
    engine.dispose()


@pytest.fixture
def repo(engine):
    connection = engine.connect()
    trans = connection.begin()
    Base.metadata.create_all(bind=connection)  # no-op on an already-migrated database
    session = Session(bind=connection, expire_on_commit=False)

    repo = SqlDiagnosisCatalogRepository(session)
    for entry in [
        CatalogDiagnosis("t10", "E11", "Diabetes mellitus tipo 2"),
        CatalogDiagnosis("t10", "E11.9", "Diabetes mellitus tipo 2 sin complicaciones"),
        CatalogDiagnosis("t10", "E11.21", "Diabetes mellitus tipo 2 con nefropatía"),
        CatalogDiagnosis("t10", "I10", "Hipertensión esencial"),
        CatalogDiagnosis("t10", "A00", "Cólera"),
        CatalogDiagnosis("t10", "J45", "Asma", billable=False),
        CatalogDiagnosis("t11", "BA00", "Hipertensión esencial"),
    ]:
        repo.upsert(entry)
    session.flush()

    yield repo
    session.close()
    trans.rollback()
    connection.close()


class TestRanking:
    def test_code_prefix_ranks_first_shorter_codes_win(self, repo):
        codes = [r.code for r in repo.search("t10", "E11")]
        assert codes == ["E11", "E11.9", "E11.21"]

    def test_lowercase_code_input_still_matches(self, repo):
        codes = [r.code for r in repo.search("t10", "e11.9")]
        assert codes[0] == "E11.9"

    def test_label_search_prefers_more_general_code(self, repo):
        codes = [r.code for r in repo.search("t10", "diabetes")]
        assert codes == ["E11", "E11.9", "E11.21"]


class TestMatching:
    def test_accent_insensitive(self, repo):
        assert [r.code for r in repo.search("t10", "colera")] == ["A00"]
        assert [r.code for r in repo.search("t10", "hipertensión")] == ["I10"]
        assert [r.code for r in repo.search("t10", "HIPERTENSION")] == ["I10"]

    def test_typo_recovered_by_trigram(self, repo):
        # No substring match: only the word_similarity branch can find these.
        assert "E11" in [r.code for r in repo.search("t10", "diabetis")]
        assert [r.code for r in repo.search("t10", "ipertension")] == ["I10"]

    def test_versions_are_isolated(self, repo):
        assert [r.code for r in repo.search("t10", "hipertension")] == ["I10"]
        assert [r.code for r in repo.search("t11", "hipertension")] == ["BA00"]

    def test_limit_is_respected(self, repo):
        assert len(repo.search("t10", "diabetes", limit=2)) == 2

    def test_like_wildcards_are_escaped(self, repo):
        # With raw LIKE, "%" would match the whole catalog.
        assert repo.search("t10", "%") == []
        assert repo.search("t10", "____") == []

    def test_billable_is_not_a_filter(self, repo):
        results = repo.search("t10", "asma")
        assert [(r.code, r.billable) for r in results] == [("J45", False)]


def test_count_by_version(repo):
    assert repo.count("t10") == 6
    assert repo.count("t11") == 1
