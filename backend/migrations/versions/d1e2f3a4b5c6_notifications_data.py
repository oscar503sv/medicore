"""notifications store structured data instead of rendered text

The table was never written to before this revision, so dropping title/body loses nothing.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-10-31 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("notifications", "title")
    op.drop_column("notifications", "body")
    op.add_column(
        "notifications",
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.create_index(
        "ix_notifications_user_created", "notifications", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.drop_column("notifications", "data")
    op.add_column(
        "notifications",
        sa.Column("body", sa.String(length=2000), nullable=False, server_default=""),
    )
    op.add_column(
        "notifications",
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
    )
