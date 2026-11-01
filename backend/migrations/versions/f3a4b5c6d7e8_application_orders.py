"""in-clinic medication applications: orders, dose records and consultation drafts

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-01 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def _tenant_fk() -> sa.Column:
    return sa.Column(
        "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )


def _patient_fk() -> sa.Column:
    return sa.Column(
        "patient_id", UUID, sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.add_column(
        "consultations",
        sa.Column(
            "draft_applications", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_table(
        "application_orders",
        sa.Column("id", UUID, primary_key=True),
        _tenant_fk(),
        _patient_fk(),
        sa.Column("drug", sa.String(120), nullable=False),
        sa.Column("dose", sa.String(60), nullable=False),
        sa.Column("route", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("doses_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("interval_hours", sa.Integer(), nullable=True),
        sa.Column("observation_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("instructions", sa.String(500), nullable=True),
        sa.Column("ordered_by_id", UUID, nullable=True),
        sa.Column("external_prescriber", sa.String(120), nullable=True),
        sa.Column("external_jvpm", sa.String(10), nullable=True),
        sa.Column("consultation_id", UUID, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by_id", UUID, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", UUID, nullable=True),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
    )
    op.create_index(
        "ix_application_orders_patient", "application_orders", ["tenant_id", "patient_id"]
    )
    op.create_index(
        "ix_application_orders_status", "application_orders", ["tenant_id", "status"]
    )
    op.create_table(
        "application_records",
        sa.Column("id", UUID, primary_key=True),
        _tenant_fk(),
        sa.Column(
            "order_id", UUID, sa.ForeignKey("application_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _patient_fk(),
        sa.Column("dose_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_id", UUID, nullable=False),
        sa.Column("lot", sa.String(60), nullable=True),
        sa.Column("lot_expiry", sa.Date(), nullable=True),
        sa.Column("site", sa.String(20), nullable=True),
        sa.Column("blood_pressure", sa.String(10), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("allergy_override", sa.String(300), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("observe_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observation_closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observation_closed_by_id", UUID, nullable=True),
        sa.Column("reaction", sa.Boolean(), nullable=True),
        sa.Column("reaction_notes", sa.String(500), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_id", UUID, nullable=True),
        sa.Column("void_reason", sa.String(300), nullable=True),
    )
    op.create_index(
        "ix_application_records_order", "application_records", ["tenant_id", "order_id"]
    )
    op.create_index(
        "ix_application_records_time", "application_records", ["tenant_id", "recorded_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_application_records_time", table_name="application_records")
    op.drop_index("ix_application_records_order", table_name="application_records")
    op.drop_table("application_records")
    op.drop_index("ix_application_orders_status", table_name="application_orders")
    op.drop_index("ix_application_orders_patient", table_name="application_orders")
    op.drop_table("application_orders")
    op.drop_column("consultations", "draft_applications")
