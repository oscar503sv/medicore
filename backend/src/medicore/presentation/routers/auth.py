"""Auth router: login, theme/locale switch."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.auth import (
    AuthenticateUser,
    AuthenticateUserCommand,
    SwitchLocale,
    SwitchTheme,
)
from medicore.domain.enums import LangPref, ThemePref
from medicore.presentation.dependencies import Actor, Clock, Hasher, JwtIssuer, UoWFactory
from medicore.presentation.schemas.auth import (
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
        role=str(session.role),
        name=session.name,
    )


@router.post("/auth/theme", status_code=204)
def switch_theme(body: SwitchThemeRequest, actor: Actor, factory: UoWFactory):
    SwitchTheme(factory).execute(actor, ThemePref(body.theme))


@router.post("/auth/locale", status_code=204)
def switch_locale(body: SwitchLocaleRequest, actor: Actor, factory: UoWFactory):
    SwitchLocale(factory).execute(actor, LangPref(body.language))
