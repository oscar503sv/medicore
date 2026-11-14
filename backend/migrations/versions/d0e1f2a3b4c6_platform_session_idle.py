"""Idle tracking for console sessions.

* ``sessions.last_activity_at``: last authenticated activity of a session, used to close
  superadmin console sessions after a period of inactivity.
* Live platform sessions are revoked: they were issued under the old 24 h lifetime and
  without activity tracking, so every superadmin signs in again after the deploy.

Revision ID: d0e1f2a3b4c6
Revises: c9d0e1f2a3b5
Create Date: 2026-11-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c6"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE sessions SET revoked_at = now() WHERE scope = 'platform' AND revoked_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("sessions", "last_activity_at")
