"""Cookie specs: names, prefixes, scope and the session-bound CSRF token."""

from __future__ import annotations

from fastapi import Response

from medicore.presentation.app import API_PREFIX
from medicore.presentation.cookies import (
    clear_session_cookies,
    csrf_token_for,
    platform_cookies,
    set_session_cookies,
    tenant_cookies,
)

SID = "6f1f4a4e-6a0e-4c43-9d6e-0b6f0d8c9a11"


def test_secure_names_carry_host_and_secure_prefixes():
    tenant = tenant_cookies(secure=True)
    console = platform_cookies(secure=True)
    assert (tenant.session, tenant.csrf) == ("__Host-mc_session", "__Host-mc_csrf")
    assert (console.session, console.csrf) == ("__Secure-mc_console", "__Host-mc_console_csrf")


def test_plain_http_names_have_no_prefix():
    tenant = tenant_cookies(secure=False)
    console = platform_cookies(secure=False)
    assert (tenant.session, tenant.csrf) == ("mc_session", "mc_csrf")
    assert (console.session, console.csrf) == ("mc_console", "mc_console_csrf")


def test_console_session_cookie_is_scoped_to_the_platform_api():
    assert platform_cookies().session_path == API_PREFIX + "/platform"
    assert tenant_cookies().session_path == "/"


def test_samesite_is_strict_for_console_and_lax_for_clinic():
    assert platform_cookies().samesite == "strict"
    assert tenant_cookies().samesite == "lax"


def test_csrf_token_is_deterministic():
    assert csrf_token_for(SID, "tenant") == csrf_token_for(SID, "tenant")


def test_csrf_token_differs_per_scope_and_session():
    base = csrf_token_for(SID, "tenant")
    assert csrf_token_for(SID, "platform") != base
    assert csrf_token_for("other-session", "tenant") != base


def test_secure_cookies_are_host_locked():
    response = Response()
    set_session_cookies(
        response, tenant_cookies(secure=True), token="t", session_id=SID, max_age=60
    )
    headers = response.headers.getlist("set-cookie")
    session = next(h for h in headers if h.startswith("__Host-mc_session="))
    assert "Secure" in session
    assert "Path=/;" in session
    assert "Domain" not in session


def test_clearing_secure_cookies_also_removes_legacy_names():
    response = Response()
    clear_session_cookies(response, platform_cookies(secure=True))
    names = {h.split("=", 1)[0] for h in response.headers.getlist("set-cookie")}
    assert {"__Secure-mc_console", "__Host-mc_console_csrf"} <= names
    assert {"mc_platform", "mc_session", "mc_csrf"} <= names
