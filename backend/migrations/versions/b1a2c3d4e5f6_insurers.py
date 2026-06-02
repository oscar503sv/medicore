"""insurers catalog + patient.insurance_id (migrating free-text insurance)

Revision ID: b1a2c3d4e5f6
Revises: a622afdfaa21
Create Date: 2026-06-01 18:00:00.000000

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "a622afdfaa21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) insurers catalog
    op.create_table(
        "insurers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("contact_person", sa.String(length=150), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_insurers_tenant_name"),
    )
    op.create_index(op.f("ix_insurers_tenant_id"), "insurers", ["tenant_id"], unique=False)

    # 2) patients.insurance_id FK (nullable)
    op.add_column("patients", sa.Column("insurance_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_patients_insurance_id", "patients", "insurers", ["insurance_id"], ["id"]
    )

    # 3) data migration: one insurer per distinct non-empty insurance text, per tenant
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT tenant_id, insurance FROM patients "
            "WHERE insurance IS NOT NULL AND insurance <> ''"
        )
    ).fetchall()
    for tenant_id, name in rows:
        insurer_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO insurers (id, tenant_id, name, active, created_at, updated_at) "
                "VALUES (:id, :tid, :name, true, now(), now())"
            ),
            {"id": insurer_id, "tid": tenant_id, "name": name},
        )
        conn.execute(
            sa.text(
                "UPDATE patients SET insurance_id = :id "
                "WHERE tenant_id = :tid AND insurance = :name"
            ),
            {"id": insurer_id, "tid": tenant_id, "name": name},
        )

    # 4) drop the old free-text column
    op.drop_column("patients", "insurance")


def downgrade() -> None:
    op.add_column("patients", sa.Column("insurance", sa.String(length=100), nullable=True))
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE patients p SET insurance = i.name "
            "FROM insurers i WHERE p.insurance_id = i.id"
        )
    )
    op.drop_constraint("fk_patients_insurance_id", "patients", type_="foreignkey")
    op.drop_column("patients", "insurance_id")
    op.drop_index(op.f("ix_insurers_tenant_id"), table_name="insurers")
    op.drop_table("insurers")
