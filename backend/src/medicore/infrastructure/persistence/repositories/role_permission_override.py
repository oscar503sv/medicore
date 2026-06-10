"""SQLAlchemy RolePermissionOverrideRepository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.role_permission_override import RolePermissionOverride
from medicore.domain.enums import Role
from medicore.domain.shared.identifiers import TenantId
from medicore.infrastructure.persistence.mappers.entities import to_role_permission_override
from medicore.infrastructure.persistence.models.role_permission_override import (
    RolePermissionOverrideModel,
)


class SqlRolePermissionOverrideRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(RolePermissionOverrideModel).filter(
            RolePermissionOverrideModel.tenant_id == self._tid
        )

    def get_by_role(self, role: Role) -> RolePermissionOverride | None:
        row = self._q().filter(RolePermissionOverrideModel.role == str(role)).first()
        return to_role_permission_override(row) if row else None

    def list(self) -> list[RolePermissionOverride]:
        rows = self._q().order_by(RolePermissionOverrideModel.role).all()
        return [to_role_permission_override(r) for r in rows]

    def save(self, override: RolePermissionOverride) -> None:
        row = self._s.get(RolePermissionOverrideModel, override.id.value)
        if row is None:
            row = RolePermissionOverrideModel(id=override.id.value)
            self._s.add(row)
        row.tenant_id = override.tenant_id.value
        row.role = str(override.role)
        row.permissions = list(override.permissions)
        row.created_at = override.created_at
        row.updated_at = override.updated_at

    def delete_by_role(self, role: Role) -> None:
        self._q().filter(RolePermissionOverrideModel.role == str(role)).delete()
