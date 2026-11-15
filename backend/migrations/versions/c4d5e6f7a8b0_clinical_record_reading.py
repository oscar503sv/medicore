"""Clinical content of records is for doctors; records list index.

* Clinics that customized the doctor role get ``records.read_clinical`` (now a doctor-only
  permission doctors must keep, like signing), as if they had not customized it.
* Index for the paginated, newest-first records list.

The downgrade removes the permission from the stored doctor customizations and drops the
index.

Revision ID: c4d5e6f7a8b0
Revises: a3b4c5d6e7f9
Create Date: 2026-11-14 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b0"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_records_tenant_encounter"
_PERMISSION = "records.read_clinical"


def upgrade() -> None:
    op.create_index(_INDEX, "medical_records", ["tenant_id", "encounter_at"])
    op.execute(
        sa.text(
            "UPDATE role_permission_overrides "
            "SET permissions = permissions || to_jsonb(CAST(:perm AS text)) "
            "WHERE role = 'doctor' AND NOT permissions ? :perm"
        ).bindparams(perm=_PERMISSION)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE role_permission_overrides SET permissions = permissions - :perm "
            "WHERE role = 'doctor'"
        ).bindparams(perm=_PERMISSION)
    )
    op.drop_index(_INDEX, table_name="medical_records")
