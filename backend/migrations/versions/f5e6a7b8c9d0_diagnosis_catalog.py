"""diagnosis catalog (ICD/CIE) with trigram search index

Revision ID: f5e6a7b8c9d0
Revises: e4d5f6a7b8c9
Create Date: 2026-06-02 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5e6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "e4d5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "diagnosis_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("version", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("search_text", sa.String(length=600), nullable=False),
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("chapter", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", "code", name="uq_diagnosis_version_code"),
    )
    op.create_index(op.f("ix_diagnosis_codes_version"), "diagnosis_codes", ["version"])
    op.create_index(
        "ix_diagnosis_search_trgm",
        "diagnosis_codes",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_search_trgm", table_name="diagnosis_codes")
    op.drop_index(op.f("ix_diagnosis_codes_version"), table_name="diagnosis_codes")
    op.drop_table("diagnosis_codes")
