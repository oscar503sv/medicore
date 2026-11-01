"""minor procedures: per-clinic catalog, procedures and consultation drafts

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-11-02 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def _tenant_fk() -> sa.Column:
    return sa.Column(
        "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def upgrade() -> None:
    op.add_column(
        "consultations",
        sa.Column(
            "draft_procedures", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_table(
        "procedure_types",
        sa.Column("id", UUID, primary_key=True),
        _tenant_fk(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("performer", sa.String(20), nullable=False),
        sa.Column("requires_consent", sa.Boolean(), nullable=False),
        sa.Column("follow_up_days", sa.Integer(), nullable=True),
        sa.Column("takes_specimen", sa.Boolean(), nullable=False),
        sa.Column("technique_template", sa.String(2000), nullable=True),
        sa.Column("instructions_template", sa.String(1000), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_procedure_types_tenant", "procedure_types", ["tenant_id"])
    op.create_table(
        "procedures",
        sa.Column("id", UUID, primary_key=True),
        _tenant_fk(),
        sa.Column("patient_id", UUID, sa.ForeignKey("patients.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("type_id", UUID, sa.ForeignKey("procedure_types.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("type_name", sa.String(120), nullable=False),
        sa.Column("performer", sa.String(20), nullable=False),
        sa.Column("requires_consent", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("indication", sa.String(500), nullable=False),
        sa.Column("ordered_by_id", UUID, nullable=False),
        sa.Column("created_by_id", UUID, nullable=False),
        sa.Column("follow_up_days", sa.Integer(), nullable=True),
        sa.Column("takes_specimen", sa.Boolean(), nullable=False),
        sa.Column("consultation_id", UUID, nullable=True),
        sa.Column("appointment_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("allergies_reviewed", sa.Boolean(), nullable=False),
        sa.Column("anticoagulants", sa.Boolean(), nullable=True),
        sa.Column("fasting", sa.Boolean(), nullable=True),
        sa.Column("allergy_override", sa.String(300), nullable=True),
        sa.Column("consent_signer", sa.String(120), nullable=True),
        sa.Column("consent_relationship", sa.String(60), nullable=True),
        sa.Column("consent_witness", sa.String(120), nullable=True),
        _ts("consent_at"),
        sa.Column("consent_by_id", UUID, nullable=True),
        sa.Column("bp_before", sa.String(10), nullable=True),
        sa.Column("hr_before", sa.Integer(), nullable=True),
        sa.Column("spo2_before", sa.Integer(), nullable=True),
        sa.Column("temp_before", sa.Float(), nullable=True),
        sa.Column("bp_after", sa.String(10), nullable=True),
        sa.Column("hr_after", sa.Integer(), nullable=True),
        sa.Column("spo2_after", sa.Integer(), nullable=True),
        sa.Column("temp_after", sa.Float(), nullable=True),
        sa.Column("anesthesia", sa.String(300), nullable=True),
        sa.Column("technique", sa.String(3000), nullable=True),
        sa.Column("findings", sa.String(2000), nullable=True),
        sa.Column("materials", sa.String(1000), nullable=True),
        sa.Column("complications", sa.String(1000), nullable=True),
        sa.Column("instructions", sa.String(2000), nullable=True),
        sa.Column("specimen_sent", sa.Boolean(), nullable=False),
        sa.Column("specimen_description", sa.String(500), nullable=True),
        _ts("started_at"),
        _ts("performed_at"),
        sa.Column("performed_by_id", UUID, nullable=True),
        sa.Column("follow_up_on", sa.Date(), nullable=True),
        _ts("cancelled_at"),
        sa.Column("cancelled_by_id", UUID, nullable=True),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("amendments", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index("ix_procedures_patient", "procedures", ["tenant_id", "patient_id"])
    op.create_index("ix_procedures_status", "procedures", ["tenant_id", "status"])
    op.create_index("ix_procedures_performed", "procedures", ["tenant_id", "performed_at"])
    op.create_index("ix_procedures_appointment", "procedures", ["tenant_id", "appointment_id"])


def downgrade() -> None:
    op.drop_table("procedures")
    op.drop_table("procedure_types")
    op.drop_column("consultations", "draft_procedures")
