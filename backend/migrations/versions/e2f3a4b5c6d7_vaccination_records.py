"""vaccination records (immunization module)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-10-31 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vaccination_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vaccine_code", sa.String(40), nullable=False),
        sa.Column("dose_key", sa.String(40), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("lot", sa.String(60), nullable=True),
        sa.Column("route", sa.String(10), nullable=True),
        sa.Column("site", sa.String(20), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("recorded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("void_reason", sa.String(300), nullable=True),
    )
    op.create_index(
        "ix_vaccination_records_patient", "vaccination_records", ["tenant_id", "patient_id"]
    )
    op.create_index(
        "ix_vaccination_records_day", "vaccination_records", ["tenant_id", "occurred_on"]
    )


def downgrade() -> None:
    op.drop_index("ix_vaccination_records_day", table_name="vaccination_records")
    op.drop_index("ix_vaccination_records_patient", table_name="vaccination_records")
    op.drop_table("vaccination_records")
