"""Custom note templates.

* ``note_templates``: note templates a clinic builds itself (name and ordered sections
  with title, role and whether required), archived instead of deleted.
* The ``custom_note_templates`` plan feature, included in Clínica Plus and Empresarial
  (plans edited from the console keep their other features).

Revision ID: c9d0e1f2a3b5
Revises: b8c9d0e1f2a4
Create Date: 2026-11-14 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b5"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FEATURE = "custom_note_templates"
_PLANS = ("clinica_plus", "empresarial")


def upgrade() -> None:
    op.create_table(
        "note_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_note_templates_tenant_id", "note_templates", ["tenant_id"])
    op.execute(sa.text(
        "UPDATE plans SET features = features || to_jsonb(CAST(:f AS text)) "
        "WHERE code = ANY(:plans) AND NOT features ? :f"
    ).bindparams(f=_FEATURE, plans=list(_PLANS)))


def downgrade() -> None:
    op.execute(sa.text("UPDATE plans SET features = features - CAST(:f AS text)").bindparams(
        f=_FEATURE))
    op.drop_index("ix_note_templates_tenant_id", table_name="note_templates")
    op.drop_table("note_templates")
