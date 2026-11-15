"""Walk-in appointments.

* ``appointments.is_walk_in``: the visit was registered on the spot, without a booked slot.
  The default is permanent so code that predates the column keeps inserting normal rows.
* ``appointments.walk_in``: doctors and receptionists have it by default, so clinics that
  customized those roles get it too, as if they had not customized them (the clinic can
  still take it away from the Permissions page). Administrators never hold it.

Revision ID: b0c1d2e3f4a6
Revises: a9b0c1d2e3f5
Create Date: 2026-11-15 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b0c1d2e3f4a6"
down_revision: Union[str, Sequence[str], None] = "a9b0c1d2e3f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMISSIONS = (
    ("doctor", "appointments.walk_in"),
    ("receptionist", "appointments.walk_in"),
)


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("is_walk_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
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
    op.drop_column("appointments", "is_walk_in")
