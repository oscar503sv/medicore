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


class SwitchThemeRequest(BaseModel):
    theme: str  # light | dark | system


class SwitchLocaleRequest(BaseModel):
    language: str  # es | en
