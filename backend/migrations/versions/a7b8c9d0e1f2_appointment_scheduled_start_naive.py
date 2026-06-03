"""store appointments.scheduled_start as naive wall-clock (timestamp without time zone)

The slot resolver and booking logic operate in the clinic's local wall-clock. Keeping the
column as ``timestamptz`` made reads come back tz-aware and serialize with a spurious ``+00:00``
offset, which the frontend then shifted. Existing values were stored as the local wall-clock
interpreted as UTC, so ``AT TIME ZONE 'UTC'`` extracts that wall-clock unchanged.

Revision ID: a7b8c9d0e1f2
Revises: f5e6a7b8c9d0
Create Date: 2026-06-03 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f5e6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE appointments "
        "ALTER COLUMN scheduled_start TYPE timestamp without time zone "
        "USING scheduled_start AT TIME ZONE 'UTC'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE appointments "
        "ALTER COLUMN scheduled_start TYPE timestamp with time zone "
        "USING scheduled_start AT TIME ZONE 'UTC'"
    )
