"""User schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InviteUserRequest(BaseModel):
    name: str
    email: str
    role: str
    password: str
    sex: str | None = None
    phone: str | None = None
    specialty: str | None = None


class UpdateRoleRequest(BaseModel):
    role: str


class UpdateUserRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    sex: str | None = None
    phone: str | None = None
    specialty: str | None = None


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
    avatar_initials: str
    last_seen_at: datetime | None
    joined_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    offset: int
    limit: int
