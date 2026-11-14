"""RFC 6238 TOTP adapter: official vectors, drift window, input hygiene and the URI."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from medicore.infrastructure.auth.totp import Rfc6238Totp

# RFC 6238 appendix B (SHA-1): ASCII secret "12345678901234567890", 8 digits.
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


def _at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


@pytest.mark.parametrize(("seconds", "expected"), RFC_VECTORS)
def test_rfc_6238_vectors(seconds, expected):
    totp = Rfc6238Totp(digits=8)
    assert totp.code_at(RFC_SECRET, _at(seconds)) == expected
    assert totp.matching_step(RFC_SECRET, expected, _at(seconds)) == seconds // 30


def test_window_accepts_one_step_either_side_but_not_two():
    totp = Rfc6238Totp()
    now = _at(1_700_000_000)
    step = totp.step_at(now)
    for offset, accepted in [(-2, False), (-1, True), (0, True), (1, True), (2, False)]:
        code = totp.code_at(RFC_SECRET, _at((step + offset) * 30))
        expected = step + offset if accepted else None
        assert totp.matching_step(RFC_SECRET, code, now) == expected


@pytest.mark.parametrize("code", ["", "12345", "1234567", "12345a", "١٢٣٤٥٦", "12 34 5"])
def test_rejects_codes_that_are_not_six_ascii_digits(code):
    assert Rfc6238Totp().matching_step(RFC_SECRET, code, _at(59)) is None


def test_spaces_in_a_code_are_ignored():
    totp = Rfc6238Totp()
    code = totp.code_at(RFC_SECRET, _at(59))
    assert totp.matching_step(RFC_SECRET, f"{code[:3]} {code[3:]}", _at(59)) is not None


def test_naive_datetimes_are_taken_as_utc():
    totp = Rfc6238Totp()
    naive = datetime(2026, 5, 31, 9, 0)
    assert totp.step_at(naive) == totp.step_at(naive.replace(tzinfo=UTC))


def test_new_secret_is_random_base32_of_160_bits():
    totp = Rfc6238Totp()
    first, second = totp.new_secret(), totp.new_secret()
    assert first != second
    assert len(first) == 32 and set(first) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def test_provisioning_uri():
    uri = Rfc6238Totp().provisioning_uri(RFC_SECRET, "super@medicore.health", "Medicore")
    parsed = urlparse(uri)
    assert parsed.scheme == "otpauth" and parsed.netloc == "totp"
    assert parsed.path == "/Medicore:super%40medicore.health"
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert query == {
        "secret": RFC_SECRET,
        "issuer": "Medicore",
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    }
