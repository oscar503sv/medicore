"""monitoring: deployed commit per server error, and scheduled-task runs

``error_events.commit`` records which deploy an error happened on, so the console can tell
new errors from old ones and whether a deploy fixed them.

``job_runs`` keeps each execution of a scheduled operational task (the nightly demo reset)
with its outcome, so the console can flag a task that failed or stopped running.

Revision ID: a1b2c3d4e5f7
Revises: f9a0b1c2d3e4
Create Date: 2026-11-11 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("error_events", sa.Column("commit", sa.String(40), nullable=True))
    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job", sa.String(60), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.String(300), nullable=False, server_default=""),
    )
    op.create_index("ix_job_runs_job_finished_at", "job_runs", ["job", "finished_at"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_job_finished_at", table_name="job_runs")
    op.drop_table("job_runs")
    op.drop_column("error_events", "commit")
