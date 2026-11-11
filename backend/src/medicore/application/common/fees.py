"""Who may decide what a doctor charges.

Setting prices and adjusting a charge (a discount, a courtesy, a procedure included in the
consultation) go together: ``fees.manage_all`` for any doctor, ``fees.manage_own`` for the
actor's own appointments and procedures. Which doctor a charge belongs to is the
appointment's doctor, or the doctor who ordered the procedure.
"""

from __future__ import annotations

from medicore.application.common.context import ActorContext
from medicore.application.common.permissions import Permission, has_permission
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import UserId


def can_price(actor: ActorContext, doctor_id: UserId) -> bool:
    if has_permission(actor, Permission.FEES_MANAGE_ALL):
        return True
    return actor.user_id == doctor_id and has_permission(actor, Permission.FEES_MANAGE_OWN)


def ensure_can_price(actor: ActorContext, doctor_id: UserId) -> None:
    if not can_price(actor, doctor_id):
        raise PermissionDenied("you may not set this doctor's fees", code="fee.not_allowed")
