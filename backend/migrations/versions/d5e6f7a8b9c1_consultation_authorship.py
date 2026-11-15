"""Consultation content is the doctor's; nursing records vitals.

* ``consultations.edit`` is now doctor-only (doctors must keep it): customized doctor roles
  get it back and doctors' per-user revocations of it are dropped, as if they had not
  restricted it.
* Customized nurse/receptionist roles that could edit consultations get
  ``consultations.vitals`` instead (what nursing actually did there), and per-user grants or
  revocations of ``consultations.edit`` for them become the same for ``consultations.vitals``.
  Where that would leave one permission both granted and revoked, the revocation wins.
* Admin rows are untouched: that role is not customizable and its adjustments are ignored.

The downgrade turns ``consultations.vitals`` back into ``consultations.edit`` for
nurse/receptionist roles and users. It cannot restore the revocations of doctors that the
upgrade dropped.

Revision ID: d5e6f7a8b9c1
Revises: c4d5e6f7a8b0
Create Date: 2026-11-14 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c1"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EDIT = "consultations.edit"
_VITALS = "consultations.vitals"
_STAFF_ROLES = "('nurse', 'receptionist')"


def _swap_permission(old: str, new: str) -> None:
    """Replace ``old`` by ``new`` in nurse/receptionist role overrides and user adjustments."""
    op.execute(
        sa.text(
            "UPDATE role_permission_overrides SET permissions = "
            "  CASE WHEN permissions ? :new THEN permissions - :old "
            "       ELSE (permissions - :old) || to_jsonb(CAST(:new AS text)) END "
            f"WHERE role IN {_STAFF_ROLES} AND permissions ? :old"
        ).bindparams(old=old, new=new)
    )
    for key in ("granted", "revoked"):
        op.execute(
            sa.text(
                "UPDATE users SET permission_adjustments = jsonb_set("
                f"  permission_adjustments, '{{{key}}}', "
                f"  CASE WHEN permission_adjustments->'{key}' ? :new "
                f"       THEN (permission_adjustments->'{key}') - :old "
                f"       ELSE ((permission_adjustments->'{key}') - :old) "
                "            || to_jsonb(CAST(:new AS text)) END) "
                f"WHERE role IN {_STAFF_ROLES} AND permission_adjustments->'{key}' ? :old"
            ).bindparams(old=old, new=new)
        )
    # An adjustment may not both grant and revoke the same permission.
    op.execute(
        sa.text(
            "UPDATE users SET permission_adjustments = jsonb_set("
            "  permission_adjustments, '{granted}', "
            "  (permission_adjustments->'granted') - :new) "
            f"WHERE role IN {_STAFF_ROLES} "
            "AND permission_adjustments->'granted' ? :new "
            "AND permission_adjustments->'revoked' ? :new"
        ).bindparams(new=new)
    )


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE role_permission_overrides "
            "SET permissions = permissions || to_jsonb(CAST(:perm AS text)) "
            "WHERE role = 'doctor' AND NOT permissions ? :perm"
        ).bindparams(perm=_EDIT)
    )
    op.execute(
        sa.text(
            "UPDATE users SET permission_adjustments = jsonb_set("
            "  permission_adjustments, '{revoked}', (permission_adjustments->'revoked') - :perm) "
            "WHERE role = 'doctor' AND permission_adjustments->'revoked' ? :perm"
        ).bindparams(perm=_EDIT)
    )
    _swap_permission(_EDIT, _VITALS)


def downgrade() -> None:
    _swap_permission(_VITALS, _EDIT)
