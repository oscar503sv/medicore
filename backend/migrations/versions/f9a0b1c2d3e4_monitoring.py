"""monitoring: recorded server errors and support sessions marked as such

``error_events`` keeps each unexpected server error (HTTP 500) for the platform console:
method, route template, status, exception type and code location only — never messages or
request data. Purged after 30 days by the application.

``sessions.impersonator_id`` marks a support (impersonation) session with the superadmin
behind it, so the console can list support access that is still open.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-11-11 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("route", sa.String(300), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(200), nullable=False),
        sa.Column("location", sa.String(300), nullable=False),
    )
    op.create_index("ix_error_events_occurred_at", "error_events", ["occurred_at"])
    op.add_column(
        "sessions", sa.Column("impersonator_id", postgresql.UUID(as_uuid=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sessions", "impersonator_id")
    op.drop_index("ix_error_events_occurred_at", table_name="error_events")
    op.drop_table("error_events")
