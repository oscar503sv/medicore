"""Auth schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    slug: str
    email: str
    password: str


class SessionResponse(BaseModel):
    user_id: str
    tenant_id: str
    tenant_name: str
    timezone: str
    role: str
    name: str
    sex: str | None = None
    must_change_password: bool = False
    permissions: list[str] = []


class SwitchThemeRequest(BaseModel):
    theme: str  # light | dark | system


class SwitchLocaleRequest(BaseModel):
    language: str  # es | en


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MyProfileResponse(BaseModel):
    name: str
    email: str
    role: str
    sex: str | None = None
    specialty: str | None = None
    phone: str | None = None
    bio: str | None = None
    permissions: list[str] = []


class UpdateMyProfileRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    bio: str | None = None


class SessionInfoResponse(BaseModel):
    id: str
    user_id: str
    user_name: str | None = None
    role: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime
    current: bool = False


class SessionListResponse(BaseModel):
    items: list[SessionInfoResponse]
