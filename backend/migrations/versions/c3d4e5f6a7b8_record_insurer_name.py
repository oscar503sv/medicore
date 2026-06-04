"""medical_records: denormalized insurer_name frozen at sign time

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-06-04 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insurer name (or NULL = self-pay) captured into the record at sign time, so the signed
    # document stays self-contained even if the appointment's insurer is later changed.
    op.add_column("medical_records", sa.Column("insurer_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("medical_records", "insurer_name")
