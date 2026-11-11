"""Analytics tiers per plan and the advanced-analytics add-on.

* ``plans.analytics_tier``: how much of the dashboard and reports the plan includes
  (basic < clinic < operations). Seeded per the published plans: Profesional independiente
  basic, Clínica clinic, Clínica Plus and Empresarial operations; any other plan basic.
* ``addon_pricing.prices`` gets the ``analytics`` add-on ($20/month) unless it is priced
  already. The clinical-modules bundle does not include it.

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f6a7b9
Create Date: 2026-11-11 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c0"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIERS = {"independiente": "basic", "clinica": "clinic", "clinica_plus": "operations",
          "empresarial": "operations"}


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("analytics_tier", sa.String(20), nullable=False, server_default="basic"),
    )
    plans = sa.table("plans", sa.column("code", sa.String), sa.column("analytics_tier", sa.String))
    for code, tier in _TIERS.items():
        op.execute(plans.update().where(plans.c.code == code).values(analytics_tier=tier))
    op.execute(
        "UPDATE addon_pricing SET prices = prices || '{\"analytics\": \"20.00\"}'::jsonb "
        "WHERE NOT prices ? 'analytics'"
    )


def downgrade() -> None:
    op.execute("UPDATE addon_pricing SET prices = prices - 'analytics'")
    op.drop_column("plans", "analytics_tier")
