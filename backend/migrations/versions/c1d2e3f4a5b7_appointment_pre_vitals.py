"""Vitals taken before the consultation starts.

* ``appointments.pre_vitals``: what nursing recorded while the patient waited for the doctor.
  They are copied into the consultation when it starts and cleared here.
* ``appointments.pre_vitals_saved_at``: when they were last changed.

The defaults are permanent so code that predates the columns keeps inserting normal rows.

Revision ID: c1d2e3f4a5b7
Revises: b0c1d2e3f4a6
Create Date: 2026-11-15 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b7"
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "pre_vitals",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("pre_vitals_saved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "pre_vitals_saved_at")
    op.drop_column("appointments", "pre_vitals")
