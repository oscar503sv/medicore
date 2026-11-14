"""Session cookie helpers — single source of cookie names, paths and flags.

The session JWT lives in an httpOnly cookie so script (XSS) can never read it. A second,
JS-readable CSRF cookie lets the SPA echo a token in a header (``X-CSRF-Token``) that
cross-site attackers cannot set. The token is an HMAC of the session id, and the server
checks the header against that recomputed value rather than against the cookie: a cookie
planted by a sibling subdomain is worthless because the attacker cannot forge the HMAC.
The CSRF cookie keeps ``Path=/`` because the SPA's JavaScript must be able to read it from
any page; only the (httpOnly) console session cookie is restricted to the platform API.

With Secure on, names carry the ``__Host-`` / ``__Secure-`` prefixes, which make the browser
refuse cookies not set over HTTPS (and, for ``__Host-``, ones scoped to a domain or sub-path).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Response

from medicore.infrastructure.config import get_settings

CSRF_HEADER = "X-CSRF-Token"
# Sent by the SPA on polling requests so they do not count as console activity.
BACKGROUND_HEADER = "X-Background-Refresh"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_KEY_LABEL = b"medicore.csrf.v1"
# Cookies of earlier releases, removed on login/logout so they cannot linger.
_LEGACY = (("mc_platform", "/"),)
_LEGACY_WHEN_SECURE = (("mc_session", "/"), ("mc_csrf", "/"))


@dataclass(frozen=True, slots=True)
class CookieSpec:
    session: str
    csrf: str
    session_path: str
    samesite: Literal["lax", "strict"]
    scope: str  # "tenant" | "platform": domain-separates the CSRF HMAC
    secure: bool


def is_mutating(method: str) -> bool:
    return method.upper() not in _SAFE_METHODS


def tenant_cookies(secure: bool | None = None) -> CookieSpec:
    secure = get_settings().secure_cookies if secure is None else secure
    prefix = "__Host-" if secure else ""
    return CookieSpec(
        session=f"{prefix}mc_session",
        csrf=f"{prefix}mc_csrf",
        session_path="/",
        samesite="lax",
        scope="tenant",
        secure=secure,
    )


def platform_cookies(secure: bool | None = None) -> CookieSpec:
    settings = get_settings()
    secure = settings.secure_cookies if secure is None else secure
    return CookieSpec(
        session=f"{'__Secure-' if secure else ''}mc_console",
        csrf=f"{'__Host-' if secure else ''}mc_console_csrf",
        session_path=settings.platform_cookie_path,
        samesite="strict",
        scope="platform",
        secure=secure,
    )


def csrf_token_for(session_id: str, scope: str) -> str:
    key = hmac.new(get_settings().jwt_secret.encode(), _CSRF_KEY_LABEL, hashlib.sha256).digest()
    digest = hmac.new(key, f"{scope}:{session_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _delete_legacy(response: Response, secure: bool) -> None:
    for name, path in _LEGACY + (_LEGACY_WHEN_SECURE if secure else ()):
        response.delete_cookie(name, path=path, secure=secure, httponly=name != "mc_csrf")


def set_session_cookies(
    response: Response, spec: CookieSpec, *, token: str, session_id: str, max_age: int
) -> None:
    """Set the httpOnly session cookie plus the CSRF cookie bound to this session."""
    response.set_cookie(
        spec.session,
        token,
        max_age=max_age,
        httponly=True,
        samesite=spec.samesite,
        secure=spec.secure,
        path=spec.session_path,
    )
    response.set_cookie(
        spec.csrf,
        csrf_token_for(session_id, spec.scope),
        max_age=max_age,
        httponly=False,  # the SPA reads it back into the X-CSRF-Token header
        samesite=spec.samesite,
        secure=spec.secure,
        path="/",
    )
    _delete_legacy(response, spec.secure)


def clear_session_cookies(response: Response, spec: CookieSpec) -> None:
    response.delete_cookie(
        spec.session,
        path=spec.session_path,
        secure=spec.secure,
        httponly=True,
        samesite=spec.samesite,
    )
    response.delete_cookie(spec.csrf, path="/", secure=spec.secure, samesite=spec.samesite)
    _delete_legacy(response, spec.secure)



def mfa_challenge_cookie_name(secure: bool | None = None) -> str:
    secure = get_settings().secure_cookies if secure is None else secure
    return f"{'__Secure-' if secure else ''}mc_console_mfa"


def _mfa_challenge_path() -> str:
    # Only the sign-in endpoints ever need it, so no other request carries the challenge.
    return f"{get_settings().platform_cookie_path}/login"


def set_mfa_challenge_cookie(response: Response, token: str, max_age: int) -> None:
    """Cookie that carries the pending second sign-in step (httpOnly, never a session)."""
    response.set_cookie(
        mfa_challenge_cookie_name(),
        token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=get_settings().secure_cookies,
        path=_mfa_challenge_path(),
    )


def clear_mfa_challenge_cookie(response: Response) -> None:
    response.delete_cookie(
        mfa_challenge_cookie_name(),
        path=_mfa_challenge_path(),
        secure=get_settings().secure_cookies,
        httponly=True,
        samesite="strict",
    )
