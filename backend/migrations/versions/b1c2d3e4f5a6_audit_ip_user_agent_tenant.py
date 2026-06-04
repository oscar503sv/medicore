"""audit context: ip_address / user_agent on both trails, tenant_id on platform audit

Phase 1 of the audit evolution: capture request network context (IP / User-Agent) on every
audit entry and correlate platform (superadmin) actions with the affected clinic via a
nullable ``tenant_id`` on ``platform_audit_logs`` (FK with ON DELETE SET NULL so the trail
survives tenant deletion).

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-06-03 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=45), nullable=True))
    op.add_column("audit_logs", sa.Column("user_agent", sa.Text(), nullable=True))

    op.add_column(
        "platform_audit_logs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "platform_audit_logs", sa.Column("ip_address", sa.String(length=45), nullable=True)
    )
    op.add_column("platform_audit_logs", sa.Column("user_agent", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_platform_audit_tenant",
        "platform_audit_logs",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_platform_audit_tenant", "platform_audit_logs", type_="foreignkey")
    op.drop_column("platform_audit_logs", "user_agent")
    op.drop_column("platform_audit_logs", "ip_address")
    op.drop_column("platform_audit_logs", "tenant_id")

    op.drop_column("audit_logs", "user_agent")
    op.drop_column("audit_logs", "ip_address")
