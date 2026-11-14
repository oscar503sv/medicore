"""Keeps every clinic with at least one active administrator."""

from __future__ import annotations

from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.user import User
from medicore.domain.enums import Role
from medicore.domain.services.admin_continuity import ensure_admin_remains


def ensure_clinic_keeps_an_admin(uow: UnitOfWork, user: User, *, stays_admin: bool) -> None:
    """Call inside the unit of work, before saving ``user``: serializes concurrent
    admin changes on the admin rows and counts what is committed."""
    if stays_admin or not (user.role == Role.ADMIN and user.is_active):
        return
    ensure_admin_remains(uow.users.lock_active_admin_ids(), user.id, stays_admin=False)
