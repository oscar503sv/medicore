"""subscriptions: editable plan catalog, add-on pricing and each clinic's subscription

Replaces tenants.plan / tenants.seat_limit (free text and an unenforced number) with a
subscription: plan (FK to the catalog), contracted add-on modules, the paid/trial period
and per-clinic overrides. The catalog starts from the published price list.

Existing clinics move to Clínica Plus with every module for 30 days, so nothing they use
today disappears on deploy; each one is then set up from the platform console.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-11-11 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, Sequence[str], None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LIMITS = ("limit_doctors", "limit_support_users", "limit_locations", "limit_storage_gb")

# code, name, monthly price, doctors, support users, locations, GB, features, order
_PLANS = [
    ("independiente", "Profesional independiente", 39, 1, 1, 1, 2, [], 1),
    ("clinica", "Clínica", 79, 3, 3, 1, 3, ["user_permissions"], 2),
    ("clinica_plus", "Clínica Plus", 119, 5, 6, 1, 5, ["user_permissions"], 3),
    ("empresarial", "Empresarial", None, None, None, None, None, ["user_permissions"], 4),
]


def upgrade() -> None:
    plans = op.create_table(
        "plans",
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("monthly_price", sa.Numeric(10, 2), nullable=True),
        *(sa.Column(c, sa.Integer(), nullable=True) for c in _LIMITS),
        sa.Column("features", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("code"),
    )
    op.bulk_insert(
        plans,
        [
            {
                "code": code, "name": name, "monthly_price": price,
                "limit_doctors": doctors, "limit_support_users": support,
                "limit_locations": locations, "limit_storage_gb": gb,
                "features": features, "active": True, "sort_order": order,
            }
            for code, name, price, doctors, support, locations, gb, features, order in _PLANS
        ],
    )

    pricing = op.create_table(
        "addon_pricing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prices", postgresql.JSONB(), nullable=False),
        sa.Column("bundle_price", sa.Numeric(10, 2), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        pricing,
        [{
            "id": 1,
            "prices": {"vaccination": "10.00", "applications": "15.00", "procedures": "15.00"},
            "bundle_price": 29,
        }],
    )

    op.add_column("tenants", sa.Column("plan_code", sa.String(length=30), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("modules", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("tenants", sa.Column("period_end", sa.Date(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tenants", sa.Column("grace_days", sa.Integer(), nullable=False, server_default="7")
    )
    for column in _LIMITS:
        op.add_column("tenants", sa.Column(column, sa.Integer(), nullable=True))
    op.add_column("tenants", sa.Column("price_override", sa.Numeric(10, 2), nullable=True))

    op.execute(
        """
        UPDATE tenants SET
            plan_code = 'clinica_plus',
            modules = '["applications", "procedures", "vaccination"]'::jsonb,
            period_end = CURRENT_DATE + 30
        """
    )
    op.alter_column("tenants", "plan_code", nullable=False)
    op.create_foreign_key(
        "fk_tenants_plan_code", "tenants", "plans", ["plan_code"], ["code"],
        onupdate="CASCADE",
    )
    op.drop_column("tenants", "plan")
    op.drop_column("tenants", "seat_limit")


def downgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("plan", sa.String(length=50), nullable=False, server_default="pro"),
    )
    op.add_column(
        "tenants",
        sa.Column("seat_limit", sa.Integer(), nullable=False, server_default="10"),
    )
    op.drop_constraint("fk_tenants_plan_code", "tenants", type_="foreignkey")
    for column in ("plan_code", "modules", "period_end", "is_trial", "grace_days",
                   *_LIMITS, "price_override"):
        op.drop_column("tenants", column)
    op.drop_table("addon_pricing")
    op.drop_table("plans")
