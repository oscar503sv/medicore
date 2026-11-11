"""What a user may do in their clinic: the role's permissions (with the clinic's
customization) limited by the subscription's contracted modules. Every place that hands
out a permission set (request actor, login, profile, support sessions) goes through here."""

from __future__ import annotations

from medicore.application.common.permissions import Permission, granted
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.tenant import Tenant
from medicore.domain.enums import Role


def granted_permissions(uow: UnitOfWork, tenant: Tenant, role: Role) -> frozenset[Permission]:
    override = uow.role_permissions.get_by_role(role)
    return granted(
        role, override.permissions if override else None, tenant.subscription.modules
    )
