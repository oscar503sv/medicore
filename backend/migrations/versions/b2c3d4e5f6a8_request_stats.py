"""monitoring: hourly request metrics per route

One row per hour, method and route template: request count, 4xx and 5xx, total and maximum
duration, and a latency histogram (fixed buckets) from which the console estimates p50/p95.
Every API worker adds its batch into the same row (upsert), so workers and restarts sum up.
Kept 30 days by the application.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-11-11 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "request_stats",
        sa.Column("hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("route", sa.String(300), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("client_errors", sa.Integer(), nullable=False),
        sa.Column("server_errors", sa.Integer(), nullable=False),
        sa.Column("total_ms", sa.Float(), nullable=False),
        sa.Column("max_ms", sa.Float(), nullable=False),
        sa.Column("buckets", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.PrimaryKeyConstraint("hour", "method", "route"),
    )


def downgrade() -> None:
    op.drop_table("request_stats")
