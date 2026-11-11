"""Consultation and procedure fees.

* ``doctor_fees``: each doctor's price per appointment type (JSONB map, USD).
* ``appointments`` / ``procedures``: the price listed when booked or ordered, what is
  charged and why they differ; procedures also note whether they were included in the
  consultation fee.
* ``procedure_types.price``: the catalog price of each procedure.
* Clinics that customized the doctor or admin role get the new fee permissions the role
  would have by default (``fees.manage_own`` / ``fees.manage_all``), as if they had not
  customized it: the clinic can still take them away from the Permissions page.

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-11-11 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FEE_COLUMNS = ("listed_fee", "fee", "fee_note")
_NEW_PERMISSIONS = {"doctor": "fees.manage_own", "admin": "fees.manage_all"}


def _fee_columns(table: str) -> None:
    op.add_column(table, sa.Column("listed_fee", sa.Numeric(10, 2), nullable=True))
    op.add_column(table, sa.Column("fee", sa.Numeric(10, 2), nullable=True))
    op.add_column(table, sa.Column("fee_note", sa.String(200), nullable=True))


def upgrade() -> None:
    op.create_table(
        "doctor_fees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "doctor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("prices", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "doctor_id", name="uq_doctor_fees_doctor"),
    )
    _fee_columns("appointments")
    _fee_columns("procedures")
    op.add_column(
        "procedures",
        sa.Column("fee_included", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("procedure_types", sa.Column("price", sa.Numeric(10, 2), nullable=True))

    for role, permission in _NEW_PERMISSIONS.items():
        op.execute(
            sa.text(
                "UPDATE role_permission_overrides "
                "SET permissions = permissions || to_jsonb(CAST(:perm AS text)) "
                "WHERE role = :role AND NOT permissions ? :perm"
            ).bindparams(role=role, perm=permission)
        )


def downgrade() -> None:
    for role, permission in _NEW_PERMISSIONS.items():
        op.execute(
            sa.text(
                "UPDATE role_permission_overrides SET permissions = permissions - :perm "
                "WHERE role = :role"
            ).bindparams(role=role, perm=permission)
        )
    op.drop_column("procedure_types", "price")
    op.drop_column("procedures", "fee_included")
    for table in ("procedures", "appointments"):
        for column in reversed(_FEE_COLUMNS):
            op.drop_column(table, column)
    op.drop_table("doctor_fees")
