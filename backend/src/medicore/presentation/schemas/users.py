"""User schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from medicore.domain.enums import Role, Sex


class InviteUserRequest(BaseModel):
    name: str
    email: str
    role: Role
    password: str
    sex: Sex | None = None
    phone: str | None = None
    specialty: str | None = None
    jvpm: str | None = None


class UpdateRoleRequest(BaseModel):
    role: Role


class UpdateUserRequest(BaseModel):
    name: str | None = None
    role: Role | None = None
    sex: Sex | None = None
    phone: str | None = None
    specialty: str | None = None
    jvpm: str | None = None


class ResetPasswordRequest(BaseModel):
    password: str


class UserResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    email: str
    role: str
    status: str
    sex: str | None = None
    specialty: str | None
    phone: str | None = None
    jvpm: str | None = None
    avatar_initials: str
    last_seen_at: datetime | None
    joined_at: datetime
    permissions_customized: bool = False


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    offset: int
    limit: int


class UpdateUserPermissionsRequest(BaseModel):
    permissions: list[str]  # the full set wanted; the role's own set clears every exception


class UserPermissionsResponse(BaseModel):
    user: UserResponse
    available: bool
    catalog: list[str]
    role_permissions: list[str]
    granted: list[str]
    revoked: list[str]
    effective: list[str]
    locked: list[str]
