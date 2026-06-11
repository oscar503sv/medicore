"""diagnosis code prefix index for autocomplete by code

Revision ID: a8b9c0d1e2f3
Revises: d4e5f6a7b8c9
Create Date: 2026-06-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # text_pattern_ops makes the index usable for LIKE 'E11%' prefix searches.
    op.create_index(
        "ix_diagnosis_version_code",
        "diagnosis_codes",
        ["version", "code"],
        postgresql_ops={"code": "text_pattern_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_diagnosis_version_code", table_name="diagnosis_codes")
