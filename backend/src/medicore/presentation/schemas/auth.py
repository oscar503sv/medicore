"""Auth schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from medicore.domain.enums import LangPref, ThemePref


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
    theme: ThemePref


class SwitchLocaleRequest(BaseModel):
    language: LangPref


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


class OnboardingStepResponse(BaseModel):
    key: str
    done: bool
    optional: bool


class OnboardingResponse(BaseModel):
    welcome_seen: bool
    dismissed: bool
    steps: list[OnboardingStepResponse]


class UpdateOnboardingRequest(BaseModel):
    welcome_seen: bool = False
    dismissed: bool = False
