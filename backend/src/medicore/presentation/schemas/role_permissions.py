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
    locked: list[str] = []  # permissions of optional modules the clinic hasn't contracted


class UpdateRolePermissionsRequest(BaseModel):
    permissions: list[str]
