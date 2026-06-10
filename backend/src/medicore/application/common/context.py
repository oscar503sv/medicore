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
    # Set when a superadmin is impersonating this clinic for support; every write is then
    # audited with an ``impersonated_by`` marker.
    impersonated_by: PlatformAdminId | None = None
    # Network context of the request, captured in the presentation layer for audit trails.
    ip_address: str | None = None
    user_agent: str | None = None
    # Effective permissions resolved per request (tenant overrides applied). Plain strings to
    # keep this module free of the application permission catalog. None → the permission
    # checks fall back to the role's code defaults (tests and scripts rely on this).
    permissions: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class PlatformActorContext:
    """A platform-level superadmin performing a cross-tenant use case (belongs to no tenant)."""

    admin_id: PlatformAdminId
    ip_address: str | None = None
    user_agent: str | None = None
