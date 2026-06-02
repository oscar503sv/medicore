"""tenant status + per-clinic ICD version

Revision ID: d3c4e5f6a7b8
Revises: c2b3d4e5f6a7
Create Date: 2026-06-02 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3c4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "c2b3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column(
        "tenants",
        sa.Column("icd_version", sa.String(length=10), nullable=False, server_default="cie11"),
    )


def downgrade() -> None:
    op.drop_column("tenants", "icd_version")
    op.drop_column("tenants", "status")
