"""Error responses carry a stable ``code`` (+ ``params``) the client translates.

Body contract: ``{"detail": <English text>, "code": str, "params": {...}}``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.support.builders import PASSWORD


def _err(resp, status: int) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"detail", "code", "params"}
    return body


def test_bad_login_has_a_code(seed, client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": "nope"},
    )
    body = _err(resp, 401)
    assert body["code"] == "auth.invalid_credentials"
    assert body["detail"] == "invalid credentials"  # English text kept for API clients


def test_missing_session_has_a_code(client):
    assert _err(client.get("/api/v1/patients"), 401)["code"] == "auth.not_authenticated"


def test_csrf_failure_has_a_code(seed, client):
    client.post(
        "/api/v1/auth/login",
        json={"slug": str(seed.tenant.slug), "email": seed.doctor.email, "password": PASSWORD},
    )
    resp = client.post("/api/v1/auth/theme", json={"theme": "dark"})
    assert _err(resp, 403)["code"] == "auth.csrf_invalid"


def test_params_travel_with_the_code(client, admin_headers, seed):
    resp = client.post(
        "/api/v1/users",
        json={
            "name": "Duplicada",
            "email": seed.doctor.email,
            "role": "nurse",
            "password": "temporal1",
        },
        headers=admin_headers,
    )
    body = _err(resp, 400)
    assert body["code"] == "user.email_taken"
    assert body["params"] == {"email": seed.doctor.email}


def test_request_validation_lists_the_bad_fields(client, admin_headers):
    resp = client.post("/api/v1/users", json={"name": "Sin email"}, headers=admin_headers)
    body = _err(resp, 422)
    assert body["code"] == "request_invalid"
    assert isinstance(body["detail"], list)  # FastAPI's shape, unchanged
    assert set(body["params"]["fields"].split(", ")) == {"email", "role", "password"}


def test_unknown_route_gets_a_generic_code(client, auth_headers):
    assert _err(client.get("/api/v1/nope", headers=auth_headers), 404)["code"] == "http.404"


class TestChangePasswordErrors:
    """A wrong current password used to be a 401, which made the client drop the session."""

    def test_wrong_current_password_is_400_and_keeps_the_session(self, client, auth_headers):
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "wrong", "new_password": "nueva-clave-1"},
            headers=auth_headers,
        )
        assert _err(resp, 400)["code"] == "password.current_incorrect"
        assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200

    def test_short_new_password_is_400_with_the_minimum(self, client, auth_headers):
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": "corta"},
            headers=auth_headers,
        )
        body = _err(resp, 400)
        assert body["code"] == "password.too_short"
        assert body["params"] == {"min": 8}


# ── Every code the backend can emit has a translation in the frontend ───────────────

_BACKEND = Path(__file__).resolve().parents[2] / "src" / "medicore"
_I18N = Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "i18n.ts"


def _backend_codes() -> set[str]:
    codes: set[str] = set()
    for f in _BACKEND.rglob("*.py"):
        text = f.read_text()
        codes |= set(re.findall(r'\bcode="([a-z_.0-9]+)"', text))  # per-raise overrides
        codes |= set(re.findall(r'^\s+code = "([a-z_.0-9]+)"$', text, re.M))  # class defaults
    codes.discard("error")  # abstract CodedError base, never raised
    return codes | {"request_invalid", "internal"}


@pytest.mark.skipif(not _I18N.exists(), reason="frontend sources not available")
def test_every_error_code_is_translated_in_both_languages():
    i18n = _I18N.read_text()
    for code in sorted(_backend_codes()):
        assert i18n.count(f"'err.{code}':") == 2, f"missing ES/EN translation for err.{code}"
