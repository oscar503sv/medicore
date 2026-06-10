"""Security response headers added by the app middleware."""

from __future__ import annotations


def test_responses_carry_security_headers(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # HSTS is production-only (tests run with the development settings).
    assert "Strict-Transport-Security" not in resp.headers


def test_error_responses_also_carry_security_headers(client):
    resp = client.get("/api/v1/patients")  # no token -> 401
    assert resp.status_code == 401
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
