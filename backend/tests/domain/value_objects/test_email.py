"""Email normalization and validation."""

from __future__ import annotations

import pytest

from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.email import is_valid_email, normalize_email, parse_email


def test_normalize_trims_and_lowercases():
    assert normalize_email("  Ana.Lopez@Clinica.TEST ") == "ana.lopez@clinica.test"


@pytest.mark.parametrize("value", ["ana@clinica.test", "a.b+c@sub.clinica.com", " A@B.CO "])
def test_valid_addresses(value):
    assert is_valid_email(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a@b",
        "a b@x.test",
        "@x.test",
        "a@@x.test",
        "a@x..test",
        "a@.test",
        f"{'a' * 65}@x.test",
        f"{'a' * 64}@{'d' * 63}.{'e' * 63}.{'f' * 62}",
    ],
)
def test_invalid_addresses(value):
    assert not is_valid_email(value)


def test_the_longest_allowed_address_is_valid():
    local = "a" * 64
    domain = "d" * 63 + "." + "e" * 63 + "." + "f" * 61
    assert len(f"{local}@{domain}") == 254
    assert is_valid_email(f"{local}@{domain}")
    assert not is_valid_email(f"{local}@{domain}f")


def test_parse_email_returns_the_normalized_address():
    assert parse_email(" Ana@Clinica.test ") == "ana@clinica.test"


def test_parse_email_rejects_with_a_code():
    with pytest.raises(InvalidValueObject) as exc:
        parse_email("no-es-email")
    assert exc.value.code == "user.invalid_email"
