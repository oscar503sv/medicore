"""One original medical record per consultation.

Signing the same consultation twice at once could store two records. The sign now locks
the consultation; this partial unique index is the database backstop. Amendments repeat
``consultation_id`` (with ``amends_record_id`` set) and are left out of it. The migration
refuses to run when duplicates already exist: they are clinical records and must be
resolved by hand, never deduplicated automatically.

Revision ID: a3b4c5d6e7f9
Revises: f2a3b4c5d6e8
Create Date: 2026-11-14 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f9"
down_revision: str | Sequence[str] | None = "f2a3b4c5d6e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_medical_records_consultation"
_WHERE = "consultation_id IS NOT NULL AND amends_record_id IS NULL"
_DUPLICATES = f"""
    SELECT tenant_id, consultation_id, count(*) AS records
    FROM medical_records
    WHERE {_WHERE}
    GROUP BY tenant_id, consultation_id
    HAVING count(*) > 1
    LIMIT 20
"""


def upgrade() -> None:
    duplicates = op.get_bind().execute(sa.text(_DUPLICATES)).all()
    if duplicates:
        listing = "; ".join(
            f"tenant={d.tenant_id} consultation={d.consultation_id}" for d in duplicates
        )
        raise RuntimeError(
            "Cannot add the unique record per consultation index: some consultations have "
            f"more than one original record ({listing}). Resolve them first, see "
            "backend/README 'Duplicate records from double signing'."
        )
    op.create_index(
        _INDEX,
        "medical_records",
        ["consultation_id"],
        unique=True,
        postgresql_where=sa.text(_WHERE),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="medical_records", postgresql_where=sa.text(_WHERE))
