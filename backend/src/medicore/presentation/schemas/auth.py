"""Auth schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from medicore.domain.enums import LangPref, ThemePref
from medicore.presentation.schemas.fields import (
    Bio,
    Jvpm,
    LoginEmail,
    Password,
    PersonName,
    Phone,
    SlugText,
)


class LoginRequest(BaseModel):
    slug: SlugText
    email: LoginEmail
    password: Password


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
    current_password: Password
    new_password: Password


class MyProfileResponse(BaseModel):
    name: str
    email: str
    role: str
    sex: str | None = None
    specialty: str | None = None
    phone: str | None = None
    bio: str | None = None
    jvpm: str | None = None
    permissions: list[str] = []
    must_change_password: bool = False
    tenant_name: str = ""
    timezone: str = ""


class UpdateMyProfileRequest(BaseModel):
    name: PersonName | None = None
    phone: Phone | None = None
    bio: Bio | None = None
    jvpm: Jvpm | None = None


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
