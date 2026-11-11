"""Metrics permissions and the clinic's practice model.

* ``tenants.practice_model``: how the clinic's doctors work (``associated`` or
  ``employed``), which shifts the default permissions on fees and income. Existing clinics
  start as associated doctors, the defaults they already had.
* Clinics that customized the doctor role get the metrics permissions the role now has by
  default (``analytics.own`` and ``analytics.money``), as if they had not customized it:
  the clinic can still take them away from the Permissions page. The admin role is never
  customized, so it picks up ``analytics.clinic`` from the code defaults.

Revision ID: e5f6a7b8c9d1
Revises: d4e5f6a7b8c0
Create Date: 2026-11-11 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMISSIONS = (("doctor", "analytics.own"), ("doctor", "analytics.money"))


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "practice_model", sa.String(20), nullable=False, server_default="associated"
        ),
    )
    for role, permission in _NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "UPDATE role_permission_overrides "
                "SET permissions = permissions || to_jsonb(CAST(:perm AS text)) "
                "WHERE role = :role AND NOT permissions ? :perm"
            ).bindparams(role=role, perm=permission)
        )


def downgrade() -> None:
    for role, permission in _NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "UPDATE role_permission_overrides SET permissions = permissions - :perm "
                "WHERE role = :role"
            ).bindparams(role=role, perm=permission)
        )
    op.drop_column("tenants", "practice_model")
