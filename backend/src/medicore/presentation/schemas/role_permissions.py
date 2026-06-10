"""Role-permission customization schemas."""

from __future__ import annotations

from pydantic import BaseModel


class RolePermissionsResponse(BaseModel):
    defaults: list[str]
    effective: list[str]
    customized: bool


class PermissionsMatrixResponse(BaseModel):
    catalog: list[str]
    roles: dict[str, RolePermissionsResponse]


class UpdateRolePermissionsRequest(BaseModel):
    permissions: list[str]
