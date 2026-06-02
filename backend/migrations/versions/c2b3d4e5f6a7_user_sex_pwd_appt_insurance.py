"""user sex + must_change_password; move insurance from patient to appointment

Revision ID: c2b3d4e5f6a7
Revises: b1a2c3d4e5f6
Create Date: 2026-06-01 23:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2b3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) users: gender + forced password change on first login
    op.add_column("users", sa.Column("sex", sa.String(length=10), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 2) appointments: per-encounter insurer (FK, nullable)
    op.add_column("appointments", sa.Column("insurance_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_insurance_id", "appointments", "insurers", ["insurance_id"], ["id"]
    )

    # 3) backfill: carry each appointment's insurer over from its patient's current insurer
    op.execute(
        "UPDATE appointments a SET insurance_id = p.insurance_id "
        "FROM patients p WHERE a.patient_id = p.id AND p.insurance_id IS NOT NULL"
    )

    # 4) drop the now-unused patient-level insurer
    op.drop_constraint("fk_patients_insurance_id", "patients", type_="foreignkey")
    op.drop_column("patients", "insurance_id")


def downgrade() -> None:
    # restore patient-level insurer (data is not back-filled from appointments)
    op.add_column("patients", sa.Column("insurance_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_patients_insurance_id", "patients", "insurers", ["insurance_id"], ["id"]
    )

    op.drop_constraint("fk_appointments_insurance_id", "appointments", type_="foreignkey")
    op.drop_column("appointments", "insurance_id")

    op.drop_column("users", "must_change_password")
    op.drop_column("users", "sex")
