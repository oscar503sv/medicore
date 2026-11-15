"""Amendments: a reason, a single chain of versions, authored by the record's author.

* ``amendment_reason`` (required on every amendment, enforced by a CHECK). Existing
  amendments get a placeholder reason.
* A unique index on ``amends_record_id``: a record is amended at most once, so the versions
  form a line. If some record was amended more than once the upgrade stops and lists them
  (ids only); resolve them by hand first, with clinical review, so that each record has at
  most one amendment (re-point the later ones at the previous version).
* Amendments made by someone other than the record's author take the author of the chain's
  root as ``author_id``, since from now on only the author amends. Who signed each version
  stays in ``signed_by_id`` and in the audit log.

The downgrade drops the column, the CHECK and the index. It cannot restore the authors it
reassigned.

Revision ID: e6f7a8b9c0d2
Revises: d5e6f7a8b9c1
Create Date: 2026-11-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d2"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_REASON = "Enmienda previa a la exigencia de motivo"

_BRANCHES = """
SELECT tenant_id, amends_record_id, array_agg(id ORDER BY signed_at) AS ids
FROM medical_records
WHERE amends_record_id IS NOT NULL
GROUP BY tenant_id, amends_record_id
HAVING count(*) > 1
LIMIT 20
"""

_REASSIGN_AUTHORS = """
WITH RECURSIVE chain AS (
    SELECT id, author_id AS root_author FROM medical_records WHERE amends_record_id IS NULL
    UNION ALL
    SELECT m.id, c.root_author FROM medical_records m JOIN chain c ON m.amends_record_id = c.id
)
UPDATE medical_records r SET author_id = chain.root_author
FROM chain
WHERE r.id = chain.id AND r.amends_record_id IS NOT NULL AND r.author_id <> chain.root_author
"""


def upgrade() -> None:
    branched = op.get_bind().execute(sa.text(_BRANCHES)).all()
    if branched:
        found = "; ".join(
            f"tenant={r.tenant_id} record={r.amends_record_id} "
            f"amendments={','.join(map(str, r.ids))}"
            for r in branched
        )
        raise RuntimeError(
            "Cannot enforce a single chain of amendments: some records were amended more "
            f"than once ({found}). Resolve them first so that each record has at most one "
            "amendment (re-point the later ones at the previous version)."
        )
    op.add_column("medical_records", sa.Column("amendment_reason", sa.String(1000), nullable=True))
    op.execute(
        sa.text(
            "UPDATE medical_records SET amendment_reason = :reason "
            "WHERE amends_record_id IS NOT NULL"
        ).bindparams(reason=LEGACY_REASON)
    )
    op.execute(sa.text(_REASSIGN_AUTHORS))
    op.create_check_constraint(
        "ck_medical_records_amendment_reason",
        "medical_records",
        "amends_record_id IS NULL OR amendment_reason IS NOT NULL",
    )
    op.create_index(
        "uq_medical_records_amends",
        "medical_records",
        ["amends_record_id"],
        unique=True,
        postgresql_where=sa.text("amends_record_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_medical_records_amends",
        table_name="medical_records",
        postgresql_where=sa.text("amends_record_id IS NOT NULL"),
    )
    op.drop_constraint("ck_medical_records_amendment_reason", "medical_records", type_="check")
    op.drop_column("medical_records", "amendment_reason")
