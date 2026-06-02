"""Auth router: login, theme/locale switch."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.auth import (
    AuthenticateUser,
    AuthenticateUserCommand,
    ChangePassword,
    SwitchLocale,
    SwitchTheme,
)
from medicore.domain.enums import LangPref, ThemePref
from medicore.presentation.dependencies import Actor, Clock, Hasher, JwtIssuer, UoWFactory
from medicore.presentation.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    SessionResponse,
    SwitchLocaleRequest,
    SwitchThemeRequest,
)

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=SessionResponse)
def login(body: LoginRequest, factory: UoWFactory, hasher: Hasher, issuer: JwtIssuer, clock: Clock):
    session = AuthenticateUser(factory, hasher, issuer, clock).execute(
        AuthenticateUserCommand(slug=body.slug, email=body.email, password=body.password)
    )
    return SessionResponse(
        token=session.token,
        user_id=str(session.user_id),
        tenant_id=str(session.tenant_id),
        tenant_name=session.tenant_name,
        role=str(session.role),
        name=session.name,
        sex=str(session.sex) if session.sex else None,
        must_change_password=session.must_change_password,
    )


@router.post("/auth/theme", status_code=204)
def switch_theme(body: SwitchThemeRequest, actor: Actor, factory: UoWFactory):
    SwitchTheme(factory).execute(actor, ThemePref(body.theme))


@router.post("/auth/locale", status_code=204)
def switch_locale(body: SwitchLocaleRequest, actor: Actor, factory: UoWFactory):
    SwitchLocale(factory).execute(actor, LangPref(body.language))


@router.post("/auth/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest, actor: Actor, factory: UoWFactory, hasher: Hasher
):
    ChangePassword(factory, hasher).execute(actor, body.current_password, body.new_password)
