"""Report exports permission.

* ``reports.export``: download a report as CSV. Doctors have it by default, so clinics that
  customized the doctor role get it too, as if they had not customized it (the clinic can
  still take it away from the Permissions page). The admin role is never customized, so it
  picks it up from the code defaults.

Revision ID: a7b8c9d0e1f3
Revises: f6a7b8c9d0e2
Create Date: 2026-11-12 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f3"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMISSIONS = (("doctor", "reports.export"),)


def upgrade() -> None:
    for role, permission in _NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "UPDATE role_permission_overrides "
                "SET permissions = permissions || to_jsonb(CAST(:perm AS text)) "
                "WHERE role = :role AND NOT permissions ? :perm"
            ).bindparams(role=role, perm=permission)
        )


def downgrade() -> None:
    for role, permission in _NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "UPDATE role_permission_overrides SET permissions = permissions - :perm "
                "WHERE role = :role"
            ).bindparams(role=role, perm=permission)
        )
