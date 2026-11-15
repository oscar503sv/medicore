"""Deleting whole tenants that hold signed clinical data (demo resets and test cleanup).

``medical_records`` refuses DELETE and ``prescriptions`` refuses it too, and the tenant foreign
keys are RESTRICT, so a clinic is never removed by accident or by a plain ``DELETE FROM
tenants``. This is the one deliberate way in: it lifts the two row triggers inside the caller's
transaction, deletes the given tenants' data children first, and puts the triggers back to
``ENABLE ALWAYS`` before returning. There is no try/finally on purpose: if anything fails the
caller's rollback restores the triggers along with the rest of the transaction.

It only ever receives the ids the caller chose, and it is not reachable from the API.
Lifting a trigger takes a lock that blocks writes to that table until the transaction ends, so
run it where that is acceptable (a nightly demo reset).

Disabling a trigger needs table ownership, which the API role deliberately lacks: call it with
a session from ``owner_session()`` (MIGRATIONS_DATABASE_URL).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Connection, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

# (table, row trigger that refuses DELETE) for the tables a purge has to empty.
_GUARDED = (
    ("medical_records", "trg_medical_records_append_only"),
    ("prescriptions", "trg_prescriptions_closing_only"),
)
# Children before parents, so no foreign key sees a dangling row.
_DATA_TABLES = (
    "medical_certificates",
    "medical_documents",
    "prescriptions",
    "medical_records",
)
_ALWAYS = "A"
_INSUFFICIENT_PRIVILEGE = "42501"


def purge_tenants(conn: Session | Connection, tenant_ids: Sequence[UUID]) -> None:
    ids = list(tenant_ids)
    if not ids:
        return
    params = {"ids": ids}
    for table, trigger in _GUARDED:
        try:
            conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        except ProgrammingError as exc:
            if getattr(exc.orig, "sqlstate", None) == _INSUFFICIENT_PRIVILEGE:
                raise RuntimeError(
                    "purge_tenants needs the schema owner (MIGRATIONS_DATABASE_URL)"
                ) from exc
            raise
    for table in _DATA_TABLES:
        conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = ANY(CAST(:ids AS uuid[]))"),
                     params)
    conn.execute(text("DELETE FROM tenants WHERE id = ANY(CAST(:ids AS uuid[]))"), params)
    for table, trigger in _GUARDED:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {trigger}"))
    enabled = conn.execute(text(
        "SELECT count(*) FROM pg_trigger WHERE tgname = ANY(CAST(:names AS text[])) "
        "AND tgenabled = :always"
    ), {"names": [trigger for _, trigger in _GUARDED], "always": _ALWAYS}).scalar_one()
    if enabled != len(_GUARDED):
        raise RuntimeError("the append-only triggers were not restored")
