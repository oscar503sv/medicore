"""Auth schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    slug: str
    email: str
    password: str


class SessionResponse(BaseModel):
    token: str
    user_id: str
    tenant_id: str
    tenant_name: str
    role: str
    name: str
    sex: str | None = None
    must_change_password: bool = False


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


class UpdateMyProfileRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    bio: str | None = None
