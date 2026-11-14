"""API tests: optional MFA of the superadmin console (sign-in step and self-service)."""

from __future__ import annotations

from datetime import timedelta

from medicore.infrastructure.auth.totp import Rfc6238Totp
from tests.support.builders import PASSWORD

TOTP = Rfc6238Totp()
LOGIN = "/api/v1/platform/login"
VERIFY = "/api/v1/platform/login/mfa"
ME = "/api/v1/platform/me"
MFA = "/api/v1/platform/me/mfa"
CHALLENGE_COOKIE = "mc_console_mfa"


def _login(seed, client):
    return client.post(LOGIN, json={"email": seed.platform_admin.email, "password": PASSWORD})


def _csrf(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("mc_console_csrf")}


def _next_period(clock) -> None:
    clock.set(clock.now() + timedelta(seconds=31))


def _enroll(seed, client, clock) -> tuple[str, list[str]]:
    """Sign in, enroll and return the secret and recovery codes; the jar ends signed out."""
    assert _login(seed, client).status_code == 200
    setup = client.post(f"{MFA}/setup", json={"password": PASSWORD}, headers=_csrf(client))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    confirm = client.post(
        f"{MFA}/confirm", json={"code": TOTP.code_at(secret, clock.now())}, headers=_csrf(client)
    )
    assert confirm.status_code == 200, confirm.text
    codes = confirm.json()["recovery_codes"]
    client.cookies.clear()
    _next_period(clock)
    return secret, codes


def _error(resp, status: int) -> dict:
    assert resp.status_code == status, resp.text
    return resp.json()


class TestLogin:
    def test_without_mfa_the_session_is_opened_as_before(self, seed, client):
        resp = _login(seed, client)
        body = resp.json()
        assert body["mfa_required"] is False and body["email"] == seed.platform_admin.email
        assert client.cookies.get("mc_console")
        assert client.cookies.get(CHALLENGE_COOKIE) is None

    def test_with_mfa_only_the_challenge_cookie_is_set(self, seed, client, clock):
        _enroll(seed, client, clock)
        resp = _login(seed, client)
        assert resp.json() == {"mfa_required": True, "admin_id": None, "name": None, "email": None}
        assert client.cookies.get(CHALLENGE_COOKIE)
        assert client.cookies.get("mc_console") is None
        assert client.cookies.get("mc_console_csrf") is None
        assert client.get(ME).status_code == 401

    def test_challenge_cookie_is_httponly_strict_and_path_scoped(self, seed, client, clock):
        _enroll(seed, client, clock)
        header = next(
            h for h in _login(seed, client).headers.get_list("set-cookie")
            if h.startswith(CHALLENGE_COOKIE)
        )
        assert "HttpOnly" in header and "SameSite=strict" in header
        assert "Path=/api/v1/platform/login" in header
        assert "Max-Age=300" in header

    def test_challenge_token_is_not_a_session(self, seed, client, clock):
        _enroll(seed, client, clock)
        _login(seed, client)
        token = client.cookies.get(CHALLENGE_COOKIE)
        client.cookies.clear()
        bearer = {"Authorization": f"Bearer {token}"}
        assert _error(client.get(ME, headers=bearer), 401)["code"] == "auth.wrong_session"
        assert _error(client.get("/api/v1/patients", headers=bearer), 401)["code"] == (
            "auth.wrong_session"
        )

    def test_a_session_token_is_not_a_challenge(self, seed, client):
        _login(seed, client)
        token = client.cookies.get("mc_console")
        client.cookies.clear()
        client.cookies.set(CHALLENGE_COOKIE, token, path="/api/v1/platform/login")
        resp = client.post(VERIFY, json={"code": "123456"})
        assert _error(resp, 401)["code"] == "auth.mfa_challenge_expired"


class TestVerify:
    def test_valid_code_opens_the_session_and_clears_the_challenge(self, seed, client, clock):
        secret, _ = _enroll(seed, client, clock)
        _login(seed, client)
        resp = client.post(VERIFY, json={"code": TOTP.code_at(secret, clock.now())})
        assert resp.status_code == 200, resp.text
        assert resp.json()["mfa_required"] is False
        assert client.cookies.get("mc_console") and client.cookies.get("mc_console_csrf")
        assert client.cookies.get(CHALLENGE_COOKIE) is None
        assert client.get(ME).status_code == 200

    def test_recovery_code_opens_the_session(self, seed, client, clock):
        _, codes = _enroll(seed, client, clock)
        _login(seed, client)
        assert client.post(VERIFY, json={"code": codes[0]}).status_code == 200
        assert client.get(ME).json()["recovery_codes_remaining"] == 9

    def test_without_a_challenge_is_401(self, client):
        resp = client.post(VERIFY, json={"code": "123456"})
        assert _error(resp, 401)["code"] == "auth.mfa_challenge_expired"

    def test_wrong_code_is_401_and_keeps_no_session(self, seed, client, clock):
        _enroll(seed, client, clock)
        _login(seed, client)
        resp = client.post(VERIFY, json={"code": "000000"})
        assert _error(resp, 401)["code"] == "auth.mfa_invalid"
        assert client.cookies.get("mc_console") is None

    def test_five_failures_then_429_with_retry_after(self, seed, client, clock):
        secret, _ = _enroll(seed, client, clock)
        for _ in range(5):
            _login(seed, client)
            assert client.post(VERIFY, json={"code": "000000"}).status_code == 401
        _login(seed, client)
        resp = client.post(VERIFY, json={"code": TOTP.code_at(secret, clock.now())})
        assert _error(resp, 429)["code"] == "auth.too_many_attempts"
        assert int(resp.headers["Retry-After"]) > 0

    def test_a_used_challenge_cannot_be_replayed(self, seed, client, clock):
        secret, _ = _enroll(seed, client, clock)
        _login(seed, client)
        token = client.cookies.get(CHALLENGE_COOKIE)
        code = TOTP.code_at(secret, clock.now())
        assert client.post(VERIFY, json={"code": code}).status_code == 200
        _next_period(clock)
        client.cookies.set(CHALLENGE_COOKIE, token, path="/api/v1/platform/login")
        resp = client.post(VERIFY, json={"code": TOTP.code_at(secret, clock.now())})
        assert _error(resp, 401)["code"] == "auth.mfa_challenge_expired"


class TestEnrollment:
    def test_me_reports_the_mfa_state(self, seed, client, clock):
        _login(seed, client)
        assert client.get(ME).json()["mfa_enabled"] is False
        _enroll_inline = client.post(
            f"{MFA}/setup", json={"password": PASSWORD}, headers=_csrf(client)
        )
        secret = _enroll_inline.json()["secret"]
        assert _enroll_inline.json()["otpauth_uri"].startswith("otpauth://totp/Medicore:")
        confirm = client.post(
            f"{MFA}/confirm",
            json={"code": TOTP.code_at(secret, clock.now())},
            headers=_csrf(client),
        )
        assert len(confirm.json()["recovery_codes"]) == 10
        me = client.get(ME).json()
        assert me["mfa_enabled"] is True and me["recovery_codes_remaining"] == 10
        assert "recovery_codes" not in me and "mfa_secret" not in me

    def test_setup_with_a_wrong_password_is_400(self, seed, client):
        _login(seed, client)
        resp = client.post(f"{MFA}/setup", json={"password": "nope"}, headers=_csrf(client))
        assert _error(resp, 400)["code"] == "password.current_incorrect"
        assert client.get(ME).status_code == 200  # a 400, so the session stays

    def test_setup_when_already_enabled_is_400(self, seed, client, clock):
        _enroll(seed, client, clock)
        _login(seed, client)
        client.post(VERIFY, json={"code": TOTP.code_at(_secret_of(seed), clock.now())})
        resp = client.post(f"{MFA}/setup", json={"password": PASSWORD}, headers=_csrf(client))
        assert _error(resp, 400)["code"] == "mfa.already_enabled"

    def test_confirm_with_a_wrong_code_is_400_not_401(self, seed, client):
        _login(seed, client)
        client.post(f"{MFA}/setup", json={"password": PASSWORD}, headers=_csrf(client))
        resp = client.post(f"{MFA}/confirm", json={"code": "000000"}, headers=_csrf(client))
        assert _error(resp, 400)["code"] == "mfa.invalid_code"
        assert client.get(ME).status_code == 200

    def test_mfa_endpoints_require_the_console_csrf_token(self, seed, client):
        _login(seed, client)
        for path, body in [
            ("setup", {"password": PASSWORD}),
            ("confirm", {"code": "123456"}),
            ("recovery-codes", {"password": PASSWORD, "code": "123456"}),
            ("disable", {"password": PASSWORD, "code": "123456"}),
        ]:
            resp = client.post(f"{MFA}/{path}", json=body)
            assert _error(resp, 403)["code"] == "auth.csrf_invalid", path

    def test_mfa_endpoints_need_a_session(self, client):
        assert client.post(f"{MFA}/setup", json={"password": PASSWORD}).status_code == 401


class TestManagement:
    def _signed_in(self, seed, client, clock):
        secret, codes = _enroll(seed, client, clock)
        _login(seed, client)
        code = TOTP.code_at(secret, clock.now())
        assert client.post(VERIFY, json={"code": code}).status_code == 200
        _next_period(clock)
        return secret, codes

    def test_regenerate_returns_new_codes_once(self, seed, client, clock):
        secret, old = self._signed_in(seed, client, clock)
        resp = client.post(
            f"{MFA}/recovery-codes",
            json={"password": PASSWORD, "code": TOTP.code_at(secret, clock.now())},
            headers=_csrf(client),
        )
        assert resp.status_code == 200, resp.text
        new = resp.json()["recovery_codes"]
        assert len(new) == 10 and not set(new) & set(old)
        assert client.get(ME).json()["recovery_codes_remaining"] == 10

    def test_regenerate_with_a_wrong_code_is_400(self, seed, client, clock):
        self._signed_in(seed, client, clock)
        resp = client.post(
            f"{MFA}/recovery-codes",
            json={"password": PASSWORD, "code": "000000"},
            headers=_csrf(client),
        )
        assert _error(resp, 400)["code"] == "mfa.invalid_code"

    def test_disable_is_204_and_the_next_login_skips_the_second_step(self, seed, client, clock):
        secret, _ = self._signed_in(seed, client, clock)
        resp = client.post(
            f"{MFA}/disable",
            json={"password": PASSWORD, "code": TOTP.code_at(secret, clock.now())},
            headers=_csrf(client),
        )
        assert resp.status_code == 204
        assert client.get(ME).json()["mfa_enabled"] is False
        client.cookies.clear()
        assert _login(seed, client).json()["mfa_required"] is False


def _secret_of(seed) -> str:
    # The store holds copies after each transaction, so read the live admin, not the seed's.
    admin = seed.factory.store.platform_admins[seed.platform_admin.id.value]
    return admin.mfa_secret.removeprefix("sealed:")
