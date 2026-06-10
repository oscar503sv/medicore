"""Per-tenant customization of a role's permission set.

When a clinic customizes a role, the override stores the role's FULL effective permission
set (not a delta). A role without an override uses the code defaults; deleting the
override restores them. The strings are validated against the catalog on write and
intersected with it on read, so a catalog change never breaks stored rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import RolePermissionOverrideId, TenantId


@dataclass(slots=True)
class RolePermissionOverride:
    """The customized permission set for one role within one tenant."""

    id: RolePermissionOverrideId
    tenant_id: TenantId
    role: Role
    permissions: tuple[str, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
