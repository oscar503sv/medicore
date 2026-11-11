"""Printable documents, medical certificates and exam orders.

* ``users.jvpm``: a doctor's registration number, printed on their documents.
* ``locations.phone``: printed in the header of the clinic's documents.
* ``tenants.print_paper`` / ``tenants.print_letterhead``: default paper for prescriptions,
  orders, certificates and slips (half letter unless the clinic changes it) and whether
  the clinic prints on pre-printed letterhead.
* ``consultations.draft_exams`` / ``medical_records.exams``: exam orders (lab, imaging)
  written in the consultation and frozen into the signed record.
* ``medical_certificates``: constancias médicas (attendance or rest days) issued from a
  signed record; voided with a reason, never edited.

Revision ID: f6a7b8c9d0e2
Revises: e5f6a7b8c9d1
Create Date: 2026-11-11 23:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e2"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("jvpm", sa.String(20), nullable=True))
    op.add_column("locations", sa.Column("phone", sa.String(50), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("print_paper", sa.String(20), nullable=False, server_default="half_letter"),
    )
    op.add_column(
        "tenants",
        sa.Column("print_letterhead", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )
    for table, column in (("consultations", "draft_exams"), ("medical_records", "exams")):
        op.add_column(
            table,
            sa.Column(column, postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'[]'::jsonb")),
        )
    op.create_table(
        "medical_certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"),
                  nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("medical_records.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rest_from", sa.Date(), nullable=True),
        sa.Column("rest_days", sa.Integer(), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("addressee", sa.String(200), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_certificates_tenant_patient", "medical_certificates",
                    ["tenant_id", "patient_id"])
    op.create_index("ix_certificates_tenant_record", "medical_certificates",
                    ["tenant_id", "record_id"])


def downgrade() -> None:
    op.drop_index("ix_certificates_tenant_record", table_name="medical_certificates")
    op.drop_index("ix_certificates_tenant_patient", table_name="medical_certificates")
    op.drop_table("medical_certificates")
    op.drop_column("medical_records", "exams")
    op.drop_column("consultations", "draft_exams")
    op.drop_column("tenants", "print_letterhead")
    op.drop_column("tenants", "print_paper")
    op.drop_column("locations", "phone")
    op.drop_column("users", "jvpm")
