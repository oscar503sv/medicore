"""ActorContext — the authenticated caller, used for permission checks and tenant scoping."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import PlatformAdminId, TenantId, UserId


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Who is performing a use case. Derived from the session token in the presentation layer."""

    user_id: UserId
    tenant_id: TenantId
    role: Role


@dataclass(frozen=True, slots=True)
class PlatformActorContext:
    """A platform-level superadmin performing a cross-tenant use case (belongs to no tenant)."""

    admin_id: PlatformAdminId
