"""Only the prescriber completes or cancels a prescription, and cancelling needs a reason.

* ``prescriptions`` gains ``closed_at``, ``closed_by_id`` and ``cancel_reason``. Closed
  prescriptions get ``closed_*`` from the first completed/cancelled audit entry; cancelled ones
  get a placeholder reason (they predate the requirement) so the new CHECK holds.
* ``prescriptions.manage`` becomes doctor-only: customized doctor roles get it back and
  doctors' per-user revocations of it are dropped; nurse/receptionist role overrides and
  user adjustments (grants and revocations) of it are removed, with no substitute.
  Admin rows are untouched: that role is not customizable and its adjustments are ignored.

The downgrade drops the CHECK and the columns. It does not restore permissions or the
revocations of doctors that the upgrade dropped.

Revision ID: f7a8b9c0d1e3
Revises: e6f7a8b9c0d2
Create Date: 2026-11-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e3"
down_revision: str | Sequence[str] | None = "e6f7a8b9c0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERM = "prescriptions.manage"
_STAFF_ROLES = "('nurse', 'receptionist')"
_LEGACY_REASON = "Cancelación previa a la exigencia de motivo"
_CHECK = "ck_prescriptions_cancel_reason"


def upgrade() -> None:
    op.add_column("prescriptions", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("prescriptions", sa.Column("closed_by_id", sa.UUID(), nullable=True))
    op.add_column("prescriptions", sa.Column("cancel_reason", sa.String(length=500), nullable=True))
    op.execute(
        sa.text(
            "UPDATE prescriptions p SET closed_at = a.ts, closed_by_id = a.actor_id "
            'FROM (SELECT DISTINCT ON (tenant_id, entity_id) tenant_id, entity_id, actor_id, "timestamp" AS ts '
            "      FROM audit_logs WHERE entity_type = 'Prescription' "
            "        AND action IN ('prescription.completed', 'prescription.cancelled') "
            '      ORDER BY tenant_id, entity_id, "timestamp") a '
            "WHERE a.tenant_id = p.tenant_id AND a.entity_id = p.id::text AND p.status <> 'active'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE prescriptions SET cancel_reason = :legacy WHERE status = 'cancelled'"
        ).bindparams(legacy=_LEGACY_REASON)
    )
    op.create_check_constraint(
        _CHECK, "prescriptions", "status <> 'cancelled' OR cancel_reason IS NOT NULL"
    )

    op.execute(
        sa.text(
            "UPDATE role_permission_overrides "
            "SET permissions = permissions || to_jsonb(CAST(:perm AS text)) "
            "WHERE role = 'doctor' AND NOT permissions ? :perm"
        ).bindparams(perm=_PERM)
    )
    op.execute(
        sa.text(
            "UPDATE users SET permission_adjustments = jsonb_set("
            "  permission_adjustments, '{revoked}', (permission_adjustments->'revoked') - :perm) "
            "WHERE role = 'doctor' AND permission_adjustments->'revoked' ? :perm"
        ).bindparams(perm=_PERM)
    )
    op.execute(
        sa.text(
            "UPDATE role_permission_overrides SET permissions = permissions - :perm "
            f"WHERE role IN {_STAFF_ROLES} AND permissions ? :perm"
        ).bindparams(perm=_PERM)
    )
    for key in ("granted", "revoked"):
        op.execute(
            sa.text(
                "UPDATE users SET permission_adjustments = jsonb_set("
                f"  permission_adjustments, '{{{key}}}', (permission_adjustments->'{key}') - :perm) "
                f"WHERE role IN {_STAFF_ROLES} AND permission_adjustments->'{key}' ? :perm"
            ).bindparams(perm=_PERM)
        )


def downgrade() -> None:
    op.drop_constraint(_CHECK, "prescriptions", type_="check")
    op.drop_column("prescriptions", "cancel_reason")
    op.drop_column("prescriptions", "closed_by_id")
    op.drop_column("prescriptions", "closed_at")
