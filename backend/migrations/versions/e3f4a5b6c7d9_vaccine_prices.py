"""Vaccine prices and the supplier of each dose given at the clinic (OZK-112).

* ``vaccine_prices``: what a clinic charges for each privately supplied vaccine. A vaccine
  without a price has no row. The vaccine catalog lives in code, so there is no foreign key.
* ``vaccination_records.supply`` (``clinic`` or ``minsal``) and ``listed_fee``: the supplier
  of a dose given at the clinic and the price copied when it was given in an appointment.
  Vaccines supplied by the health ministry are free by law (Decreto 1013, arts. 5, 12, 13
  and 26), which a CHECK enforces next to the domain rule.
* ``ck_appointments_vaccination_fee_cap``: a vaccination visit is charged at most what its
  doses add up to (it can be discounted, never raised).

No backfill: earlier doses keep ``supply`` NULL ("not recorded"). Compatible with the
previous release: it inserts NULL in both columns, which satisfies every CHECK (its
vaccination visits keep an empty charge).

Downgrade refuses to run while prices or supplied doses exist instead of deleting them.

Revision ID: e3f4a5b6c7d9
Revises: d2e3f4a5b6c8
Create Date: 2026-11-15 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4a5b6c7d9"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RECORD_CHECKS = {
    "ck_vaccination_records_supply_value": "supply IS NULL OR supply IN ('clinic', 'minsal')",
    "ck_vaccination_records_supply_scope": (
        "supply IS NULL OR (source = 'clinic' AND outcome = 'administered')"
    ),
    "ck_vaccination_records_fee_range": (
        "listed_fee IS NULL OR (listed_fee >= 0 AND listed_fee <= 10000)"
    ),
    "ck_vaccination_records_fee_needs_visit": (
        "listed_fee IS NULL OR (supply IS NOT NULL AND appointment_id IS NOT NULL)"
    ),
    "ck_vaccination_records_minsal_free": (
        "supply IS DISTINCT FROM 'minsal' OR listed_fee IS NULL OR listed_fee = 0"
    ),
}


def upgrade() -> None:
    op.create_table(
        "vaccine_prices",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vaccine_code", sa.String(length=40), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "vaccine_code"),
        sa.CheckConstraint("price >= 0 AND price <= 10000", name="ck_vaccine_prices_range"),
    )

    op.add_column("vaccination_records", sa.Column("supply", sa.String(length=10), nullable=True))
    op.add_column(
        "vaccination_records", sa.Column("listed_fee", sa.Numeric(10, 2), nullable=True)
    )
    for name, expression in _RECORD_CHECKS.items():
        op.create_check_constraint(name, "vaccination_records", expression)

    op.create_check_constraint(
        "ck_appointments_vaccination_fee_cap", "appointments",
        "type <> 'vaccination' OR listed_fee IS NULL OR fee <= listed_fee",
    )


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM vaccine_prices) "
        "+ (SELECT count(*) FROM vaccination_records "
        "   WHERE supply IS NOT NULL OR listed_fee IS NOT NULL)"
    )).scalar_one()
    if in_use:
        raise RuntimeError(
            "cannot downgrade: vaccine prices or doses with a recorded supplier exist; "
            "move or remove them first, nothing is deleted automatically"
        )

    op.drop_constraint("ck_appointments_vaccination_fee_cap", "appointments", type_="check")
    for name in _RECORD_CHECKS:
        op.drop_constraint(name, "vaccination_records", type_="check")
    op.drop_column("vaccination_records", "listed_fee")
    op.drop_column("vaccination_records", "supply")
    op.drop_table("vaccine_prices")
