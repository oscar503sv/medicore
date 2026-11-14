"""Optional second factor (TOTP) for superadmins.

* ``platform_admins``: sealed TOTP secret, the pending one while enrolling, when MFA was
  enabled and the last accepted time step (anti-replay). All nullable: MFA is opt-in.
* ``platform_admin_recovery_codes``: single-use recovery codes, stored as SHA-256 hashes.

Revision ID: e1f2a3b4c5d7
Revises: d0e1f2a3b4c6
Create Date: 2026-11-14 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f2a3b4c5d7"
down_revision: str | Sequence[str] | None = "d0e1f2a3b4c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("platform_admins", sa.Column("mfa_secret", sa.Text(), nullable=True))
    op.add_column("platform_admins", sa.Column("mfa_pending_secret", sa.Text(), nullable=True))
    op.add_column(
        "platform_admins", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("platform_admins", sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
    op.create_table(
        "platform_admin_recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_admins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("admin_id", "code_hash"),
    )
    op.create_index(
        "ix_platform_admin_recovery_codes_admin_id", "platform_admin_recovery_codes", ["admin_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_admin_recovery_codes_admin_id", table_name="platform_admin_recovery_codes"
    )
    op.drop_table("platform_admin_recovery_codes")
    op.drop_column("platform_admins", "mfa_last_step")
    op.drop_column("platform_admins", "mfa_enabled_at")
    op.drop_column("platform_admins", "mfa_pending_secret")
    op.drop_column("platform_admins", "mfa_secret")
