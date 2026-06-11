"""Auth router: login/logout, theme/locale switch."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from medicore.application.use_cases.auth import (
    AuthenticateUser,
    AuthenticateUserCommand,
    ChangePassword,
    GetMyProfile,
    SwitchLocale,
    SwitchTheme,
    UpdateMyProfile,
)
from medicore.domain.enums import LangPref, ThemePref
from medicore.infrastructure.config import get_settings
from medicore.presentation.cookies import (
    SESSION_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from medicore.presentation.dependencies import (
    Actor,
    Clock,
    Hasher,
    JwtIssuer,
    UoWFactory,
    _client_ip,
    revoke_session_token,
)
from medicore.presentation.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MyProfileResponse,
    SessionResponse,
    SwitchLocaleRequest,
    SwitchThemeRequest,
    UpdateMyProfileRequest,
)
from medicore.presentation.serializers import ser_my_profile

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=SessionResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    factory: UoWFactory,
    hasher: Hasher,
    issuer: JwtIssuer,
    clock: Clock,
):
    session = AuthenticateUser(factory, hasher, issuer, clock).execute(
        AuthenticateUserCommand(
            slug=body.slug,
            email=body.email,
            password=body.password,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    # The JWT travels only in an httpOnly cookie — never in the body, never in storage.
    set_session_cookies(
        response,
        cookie_name=SESSION_COOKIE,
        token=session.token,
        max_age=get_settings().jwt_expire_minutes * 60,
    )
    return SessionResponse(
        user_id=str(session.user_id),
        tenant_id=str(session.tenant_id),
        tenant_name=session.tenant_name,
        timezone=session.timezone,
        role=str(session.role),
        name=session.name,
        sex=str(session.sex) if session.sex else None,
        must_change_password=session.must_change_password,
        permissions=list(session.permissions),
    )


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    factory: UoWFactory,
    issuer: JwtIssuer,
    clock: Clock,
):
    """Revoke the server-side session (best effort) and clear the cookies.

    No auth required: with a valid token this is a real logout, without one there is
    simply nothing to revoke.
    """
    revoke_session_token(request.cookies.get(SESSION_COOKIE), issuer, factory, clock.now())
    clear_session_cookies(response, SESSION_COOKIE)


@router.post("/auth/theme", status_code=204)
def switch_theme(body: SwitchThemeRequest, actor: Actor, factory: UoWFactory):
    SwitchTheme(factory).execute(actor, ThemePref(body.theme))


@router.post("/auth/locale", status_code=204)
def switch_locale(body: SwitchLocaleRequest, actor: Actor, factory: UoWFactory):
    SwitchLocale(factory).execute(actor, LangPref(body.language))


@router.post("/auth/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest, actor: Actor, factory: UoWFactory, hasher: Hasher, clock: Clock
):
    ChangePassword(factory, hasher, clock).execute(
        actor, body.current_password, body.new_password
    )


@router.get("/auth/me", response_model=MyProfileResponse)
def get_my_profile(actor: Actor, factory: UoWFactory):
    return ser_my_profile(GetMyProfile(factory).execute(actor))


@router.patch("/auth/me", response_model=MyProfileResponse)
def update_my_profile(
    body: UpdateMyProfileRequest, actor: Actor, factory: UoWFactory, clock: Clock
):
    profile = UpdateMyProfile(factory, clock).execute(
        actor, name=body.name, phone=body.phone, bio=body.bio
    )
    return ser_my_profile(profile)
