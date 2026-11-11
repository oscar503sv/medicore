"""per-user permissions: each user's exceptions to their role's permissions

Plans with the per-user permissions feature (Clínica and up) let the clinic grant a user
a few extra permissions or revoke some of their role's. Stored on the user as
{"granted": [...], "revoked": [...]}; empty for everyone today.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-11-11 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "permission_adjustments", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "permission_adjustments")
