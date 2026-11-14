"""Sign-in throttle: remember the last success per account and IP.

* ``login_attempts.last_success_at``: when the account last signed in from that IP. Such an
  IP is exempt from the account-wide cap, so an attacker spreading guesses over many
  addresses cannot lock the owner out of the place they always sign in from. Nullable: only
  the account-and-IP rows ever get a value.

Revision ID: f2a3b4c5d6e8
Revises: e1f2a3b4c5d7
Create Date: 2026-11-14 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e8"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "login_attempts", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("login_attempts", "last_success_at")
