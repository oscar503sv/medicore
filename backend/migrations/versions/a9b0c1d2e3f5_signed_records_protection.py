"""Signed records are protected in the database.

What the application promises (a signed record is never edited; corrections are new rows) is
now enforced by the database too:

* ``medical_records`` is append-only: a trigger refuses UPDATE, DELETE and TRUNCATE (it is
  ``ENABLE ALWAYS``, so it also fires for sessions in ``replica`` mode).
* Every record carries a SHA-256 seal chained to the one it amends (``seal``,
  ``seal_version``); the existing records are sealed here, so the seal certifies them as they
  are at the date of this migration.
* ``medical_records``, ``prescriptions`` and ``medical_documents`` get real foreign keys
  (all ``RESTRICT``, the tenant one too: deleting a clinic with clinical data is refused) and
  the indexes they need.
* A prescription can only be closed: active -> completed/cancelled, changing nothing else.
* ``medical_records.created_at`` records when the row was inserted.

``record_id`` of a prescription or document that points at no record becomes NULL (the file
or prescription stays with its patient). Any other dangling reference aborts the migration
with the table and ids, never with clinical data: fix it by hand (see the backend README)
and run it again.

The backfill imports the application's seal v1 code, an exception to the rule that migrations
do not import the application: the canonical form is frozen on purpose (changing it would
break every stored seal), and the SQL test of the seal covers it.

Downgrade removes the triggers, the new columns, indexes and foreign keys, and puts the
tenant ones back on CASCADE.

Revision ID: a9b0c1d2e3f5
Revises: f8a9b0c1d2e4
Create Date: 2026-11-15 18:00:00.000000

"""

from collections.abc import Sequence
from types import SimpleNamespace

import sqlalchemy as sa
from alembic import context, op

revision: str = "a9b0c1d2e3f5"
down_revision: str | Sequence[str] | None = "f8a9b0c1d2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("medical_records", "prescriptions", "medical_documents")
_BATCH = 500
_ORPHAN_SAMPLE = 20

# (table, column, parent table): the references that were not foreign keys until now.
_NEW_FKS = (
    ("medical_records", "patient_id", "patients"),
    ("medical_records", "author_id", "users"),
    ("medical_records", "signed_by_id", "users"),
    ("medical_records", "appointment_id", "appointments"),
    ("medical_records", "consultation_id", "consultations"),
    ("prescriptions", "patient_id", "patients"),
    ("prescriptions", "prescriber_id", "users"),
    ("prescriptions", "closed_by_id", "users"),
    ("prescriptions", "record_id", "medical_records"),
    ("medical_documents", "patient_id", "patients"),
    ("medical_documents", "uploaded_by_id", "users"),
    ("medical_documents", "record_id", "medical_records"),
)

_INDEXES = (
    ("ix_medical_records_consultation_id", "medical_records", "consultation_id"),
    ("ix_medical_records_appointment_id", "medical_records", "appointment_id"),
    ("ix_medical_records_patient_id", "medical_records", "patient_id"),
    ("ix_prescriptions_record_id", "prescriptions", "record_id"),
    ("ix_medical_documents_record_id", "medical_documents", "record_id"),
)

_TRIGGERS = (
    ("medical_records", "trg_medical_records_append_only"),
    ("medical_records", "trg_medical_records_no_truncate"),
    ("prescriptions", "trg_prescriptions_closing_only"),
    ("prescriptions", "trg_prescriptions_no_truncate"),
)

_RECORDS_FUNCTION = """
CREATE FUNCTION medical_records_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
    MESSAGE = format('medical_records is append-only: %s is not allowed', TG_OP),
    HINT = 'Correct a signed record with an amendment (a new row).';
  RETURN NULL;
END $$
"""

_PRESCRIPTIONS_FUNCTION = """
CREATE FUNCTION prescriptions_closing_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE frozen public.prescriptions;
BEGIN
  IF TG_OP <> 'UPDATE' THEN
    RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
      MESSAGE = format('prescriptions: %s is not allowed', TG_OP);
  END IF;
  IF NEW IS NOT DISTINCT FROM OLD THEN
    RETURN NEW;
  END IF;
  frozen := NEW;
  frozen.status := OLD.status;
  frozen.closed_at := OLD.closed_at;
  frozen.closed_by_id := OLD.closed_by_id;
  frozen.cancel_reason := OLD.cancel_reason;
  IF OLD.status <> 'active' OR NEW.status NOT IN ('completed', 'cancelled')
     OR frozen IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
      MESSAGE = 'prescriptions: only an active prescription is closed, and nothing else changes';
  END IF;
  RETURN NEW;
END $$
"""


def _unlink_orphan_record_ids(conn: sa.Connection) -> None:
    for table in ("prescriptions", "medical_documents"):
        conn.execute(sa.text(
            f"UPDATE {table} x SET record_id = NULL WHERE x.record_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM medical_records r WHERE r.id = x.record_id)"
        ))


def _orphans(conn: sa.Connection, table: str, column: str, parent: str) -> list[str]:
    rows = conn.execute(sa.text(
        f"SELECT x.id FROM {table} x WHERE x.{column} IS NOT NULL AND NOT EXISTS "
        f"(SELECT 1 FROM {parent} p WHERE p.id = x.{column}) LIMIT {_ORPHAN_SAMPLE}"
    )).all()
    return [str(r[0]) for r in rows]


def _refuse_dangling_references(conn: sa.Connection) -> None:
    problems = []
    for table, column, parent in _NEW_FKS:
        ids = _orphans(conn, table, column, parent)
        if ids:
            problems.append(f"{table}.{column} -> {parent}: {', '.join(ids)}")
    if problems:
        raise RuntimeError(
            "Dangling references block adding the foreign keys (first "
            f"{_ORPHAN_SAMPLE} ids of each); fix them and run the migration again:\n  "
            + "\n  ".join(problems)
        )


def _seal_existing_records(conn: sa.Connection) -> None:
    # Imported here, not at module level: only this step needs the application, and a frozen
    # copy of the seal would be one more thing to keep in step.
    from medicore.domain.services.record_seal import seal_v1
    from medicore.infrastructure.persistence.mappers.entities import to_medical_record

    seals: dict[object, object] = {}
    level_ids: list[object] | None = None  # None = the originals
    while True:
        if level_ids is None:
            where, params = "amends_record_id IS NULL", {}
        elif not level_ids:
            break
        else:
            where, params = "amends_record_id = ANY(:ids)", {"ids": level_ids}
        result = conn.execute(
            sa.text(f"SELECT * FROM medical_records WHERE {where} ORDER BY id"), params
        )
        next_ids: list[object] = []
        while batch := result.fetchmany(_BATCH):
            updates = []
            for row in batch:
                record = to_medical_record(SimpleNamespace(**row._mapping))
                previous = seals.get(row.amends_record_id) if row.amends_record_id else None
                seal = seal_v1(record, previous)  # type: ignore[arg-type]
                seals[row.id] = seal
                next_ids.append(row.id)
                updates.append({"id": row.id, "seal": seal.digest, "version": seal.version})
            conn.execute(
                sa.text("UPDATE medical_records SET seal = :seal, seal_version = :version "
                        "WHERE id = :id"),
                updates,
            )
        level_ids = next_ids


def _tenant_fk_name(conn: sa.Connection, table: str) -> str:
    return conn.execute(sa.text(
        "SELECT conname FROM pg_constraint WHERE contype = 'f' "
        "AND conrelid = CAST(:t AS regclass) AND confrelid = 'tenants'::regclass"
    ), {"t": table}).scalar_one()


def _recreate_tenant_fk(conn: sa.Connection, table: str, ondelete: str) -> None:
    op.drop_constraint(_tenant_fk_name(conn, table), table, type_="foreignkey")
    op.create_foreign_key(
        f"{table}_tenant_id_fkey", table, "tenants", ["tenant_id"], ["id"], ondelete=ondelete
    )


def upgrade() -> None:
    if context.is_offline_mode():
        # The backfill reads the data: it cannot be written as a script.
        raise RuntimeError("This migration reads and seals existing records: run it online")
    conn = op.get_bind()

    _unlink_orphan_record_ids(conn)
    _refuse_dangling_references(conn)

    op.add_column("medical_records", sa.Column("created_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE medical_records SET created_at = signed_at")
    op.alter_column("medical_records", "created_at", server_default=sa.text("now()"),
                    nullable=False)

    op.add_column("medical_records", sa.Column("seal", sa.String(64)))
    op.add_column("medical_records", sa.Column("seal_version", sa.SmallInteger()))
    _seal_existing_records(conn)
    op.alter_column("medical_records", "seal", nullable=False)
    op.alter_column("medical_records", "seal_version", nullable=False)
    op.create_check_constraint(
        "ck_medical_records_seal", "medical_records",
        "seal ~ '^[0-9a-f]{64}$' AND seal_version >= 1",
    )

    for table in _TABLES:
        _recreate_tenant_fk(conn, table, "RESTRICT")
    for table, column, parent in _NEW_FKS:
        op.create_foreign_key(
            f"{table}_{column}_fkey", table, parent, [column], ["id"], ondelete="RESTRICT"
        )
    for name, table, column in _INDEXES:
        op.create_index(name, table, [column])

    op.execute(_RECORDS_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_medical_records_append_only BEFORE UPDATE OR DELETE "
        "ON medical_records FOR EACH ROW EXECUTE FUNCTION medical_records_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_medical_records_no_truncate BEFORE TRUNCATE "
        "ON medical_records FOR EACH STATEMENT EXECUTE FUNCTION medical_records_append_only()"
    )
    op.execute(_PRESCRIPTIONS_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_prescriptions_closing_only BEFORE UPDATE OR DELETE "
        "ON prescriptions FOR EACH ROW EXECUTE FUNCTION prescriptions_closing_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_prescriptions_no_truncate BEFORE TRUNCATE "
        "ON prescriptions FOR EACH STATEMENT EXECUTE FUNCTION prescriptions_closing_only()"
    )
    for table, trigger in _TRIGGERS:
        # ALWAYS: sessions in replica mode (session_replication_role) do not skip them.
        op.execute(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {trigger}")


def downgrade() -> None:
    conn = op.get_bind()
    for table, trigger in _TRIGGERS:
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
    op.execute("DROP FUNCTION prescriptions_closing_only()")
    op.execute("DROP FUNCTION medical_records_append_only()")

    for name, table, _column in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    for table, column, _parent in reversed(_NEW_FKS):
        op.drop_constraint(f"{table}_{column}_fkey", table, type_="foreignkey")
    for table in _TABLES:
        _recreate_tenant_fk(conn, table, "CASCADE")

    op.drop_constraint("ck_medical_records_seal", "medical_records", type_="check")
    op.drop_column("medical_records", "seal_version")
    op.drop_column("medical_records", "seal")
    op.drop_column("medical_records", "created_at")
