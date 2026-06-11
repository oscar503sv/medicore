"""Session cookie helpers — single source of cookie names and flags.

The session JWT lives in an httpOnly cookie so script (XSS) can never read it. A second,
JS-readable CSRF cookie implements the double-submit pattern: browsers attach cookies
automatically, so cookie-authenticated mutations must echo the CSRF value in a header
(``X-CSRF-Token``) that cross-site attackers cannot set.
"""

from __future__ import annotations

import secrets

from fastapi import Response

from medicore.infrastructure.config import get_settings

SESSION_COOKIE = "mc_session"
PLATFORM_COOKIE = "mc_platform"
CSRF_COOKIE = "mc_csrf"
CSRF_HEADER = "X-CSRF-Token"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_mutating(method: str) -> bool:
    return method.upper() not in _SAFE_METHODS


def set_session_cookies(response: Response, *, cookie_name: str, token: str, max_age: int) -> None:
    """Set the httpOnly session cookie plus a fresh CSRF cookie (rotated on every login)."""
    secure = get_settings().is_production  # dev runs on plain http://localhost
    response.set_cookie(
        cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=max_age,
        httponly=False,  # the SPA reads it back into the X-CSRF-Token header
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_session_cookies(response: Response, cookie_name: str) -> None:
    response.delete_cookie(cookie_name, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
