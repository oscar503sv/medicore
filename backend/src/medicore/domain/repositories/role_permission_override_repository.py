"""RolePermissionOverrideRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.role_permission_override import RolePermissionOverride
from medicore.domain.enums import Role


class RolePermissionOverrideRepository(Protocol):
    def get_by_role(self, role: Role) -> RolePermissionOverride | None: ...

    def list(self) -> list[RolePermissionOverride]: ...

    def save(self, override: RolePermissionOverride) -> None: ...

    def delete_by_role(self, role: Role) -> None: ...
