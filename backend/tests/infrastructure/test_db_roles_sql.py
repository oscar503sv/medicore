"""The database roles of scripts/db_roles.sql (PostgreSQL).

SKIPS unless the test database went through that script: the roles must exist, the connecting
user must be able to SET ROLE to the application role, and the grants must be in place.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from medicore.infrastructure.config import get_settings

APP_ROLE = "medicore_app"
OWNER_ROLE = "medicore_owner"
INSUFFICIENT_PRIVILEGE = "42501"


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            roles = conn.execute(text(
                "SELECT count(*) FROM pg_roles WHERE rolname IN (:app, :owner)"
            ), {"app": APP_ROLE, "owner": OWNER_ROLE}).scalar_one()
            if roles != 2:
                pytest.skip("scripts/db_roles.sql has not been applied to this database")
            if not conn.execute(text(
                "SELECT has_table_privilege(:app, 'medical_records', 'SELECT')"
            ), {"app": APP_ROLE}).scalar_one():
                pytest.skip("medicore_app has no grants here: apply scripts/db_roles.sql")
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("PostgreSQL not available")
    yield engine
    engine.dispose()


@pytest.fixture
def app_conn(engine):
    """A connection acting as the application role inside a transaction that never commits."""
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        except DBAPIError:
            outer.rollback()
            pytest.skip("the test user cannot SET ROLE medicore_app")
        yield conn
        outer.rollback()


def assert_refused(conn, statement: str) -> None:
    with pytest.raises(DBAPIError) as refused, conn.begin_nested():
        conn.execute(text(statement))
    assert getattr(refused.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize("statement", [
    "ALTER TABLE medical_records DISABLE TRIGGER trg_medical_records_append_only",
    "ALTER TABLE prescriptions DISABLE TRIGGER trg_prescriptions_closing_only",
    "DROP TABLE medical_records",
    "UPDATE medical_records SET seal = seal",
    "DELETE FROM medical_records",
    "TRUNCATE medical_records",
    "DELETE FROM prescriptions",
    "TRUNCATE prescriptions",
    "UPDATE audit_logs SET action = action",
    "DELETE FROM audit_logs",
    "UPDATE platform_audit_logs SET action = action",
    "DELETE FROM platform_audit_logs",
    "CREATE TABLE rogue (id int)",
    "CREATE TEMP TABLE rogue (id int)",
    "SET session_replication_role = replica",
    "INSERT INTO alembic_version (version_num) VALUES ('rogue')",
    "UPDATE alembic_version SET version_num = version_num",
])
def test_the_application_role_cannot_do_it(app_conn, statement):
    assert_refused(app_conn, statement)


@pytest.mark.parametrize("statement", [
    "SELECT id FROM medical_records LIMIT 1 FOR UPDATE",
    "SELECT id FROM medical_records LIMIT 1 FOR NO KEY UPDATE",
    "SELECT id FROM prescriptions LIMIT 1 FOR UPDATE",
    "SELECT id FROM prescriptions LIMIT 1 FOR NO KEY UPDATE",
    "SELECT version_num FROM alembic_version",
    "SET LOCAL pg_trgm.word_similarity_threshold = 0.3",
])
def test_the_application_role_keeps_what_the_api_needs(app_conn, statement):
    app_conn.execute(text(statement))


# Filtering by schema inside a subquery: the privilege functions must not run on the tables of
# other schemas (pg_catalog.pg_statistic is not visible through "public.").
PUBLIC_TABLES = (
    "(SELECT tablename FROM pg_tables WHERE schemaname = 'public' OFFSET 0) AS t"
)


def test_every_table_but_alembic_version_is_readable_and_insertable(app_conn):
    missing = app_conn.execute(text(
        f"SELECT tablename FROM {PUBLIC_TABLES} WHERE tablename <> 'alembic_version' AND NOT ("
        "has_table_privilege(current_user, format('public.%I', tablename), 'SELECT') AND "
        "has_table_privilege(current_user, format('public.%I', tablename), 'INSERT'))"
    )).scalars().all()
    assert missing == []


def test_the_application_role_can_never_truncate(app_conn):
    truncatable = app_conn.execute(text(
        f"SELECT tablename FROM {PUBLIC_TABLES} "
        "WHERE has_table_privilege(current_user, format('public.%I', tablename), 'TRUNCATE')"
    )).scalars().all()
    assert truncatable == []


def test_the_schema_belongs_to_the_owner_role(engine):
    with engine.connect() as conn:
        strangers = conn.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','S','f') "
            "AND c.relowner <> CAST(:owner AS regrole) "
            "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass "
            "AND d.objid = c.oid AND d.deptype IN ('e','a','i')) "
            "UNION ALL SELECT p.proname FROM pg_proc p JOIN pg_namespace n "
            "ON n.oid = p.pronamespace WHERE n.nspname = 'public' "
            "AND p.proowner <> CAST(:owner AS regrole) "
            "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass "
            "AND d.objid = p.oid AND d.deptype = 'e')"
        ), {"owner": OWNER_ROLE}).scalars().all()
    assert strangers == []
