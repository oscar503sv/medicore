"""Password policy: length, a light composition rule, blocklist, nothing personal."""

from __future__ import annotations

import pytest

from medicore.domain.services.password_policy import MAX_BYTES, MIN_LENGTH, ensure_acceptable
from medicore.domain.shared.errors import InvalidValueObject


def _code(password: str, personal=()) -> str:
    with pytest.raises(InvalidValueObject) as exc:
        ensure_acceptable(password, personal=personal)
    return exc.value.code


@pytest.mark.parametrize(
    "password", ["Rio-Lempa-482", "volcán de izalco 7", "Café con pan 2", "x9#Lm2!pQz"]
)
def test_acceptable_passwords(password):
    ensure_acceptable(password, personal=("Ana Lucía Portillo", "ana@clinica-norte.test"))


def test_too_short():
    assert _code("Ab1-cd2") == "password.too_short"
    with pytest.raises(InvalidValueObject) as exc:
        ensure_acceptable("x" * (MIN_LENGTH - 1))
    assert exc.value.params == {"min": MIN_LENGTH}


def test_too_long_for_bcrypt():
    assert _code("a1" * (MAX_BYTES // 2 + 1)) == "password.too_long"
    # Accented letters take two bytes each.
    assert _code("ñ" * 37 + "1") == "password.too_long"


@pytest.mark.parametrize(
    "password", ["solamenteletras", "1234567890", "aaaaaaaaa1", "ab1ab1ab1ab1"]
)
def test_too_simple(password):
    assert _code(password) == "password.too_simple"


@pytest.mark.parametrize(
    "password",
    ["Contraseña1", "Clinica2024!", "Medicore123", "P-a-s-s-w-o-r-d-1", "Bienvenido2025"],
)
def test_common_passwords(password):
    assert _code(password) == "password.common"


@pytest.mark.parametrize(
    ("password", "personal"),
    [
        ("Portillo#2024", ("Ana Lucía Portillo",)),
        ("mi-lucia-99", ("Ana Lucía Portillo",)),
        ("analucia.p-1", ("x", "analucia.portillo@centro-norte.test")),
        ("norte-clinic-1", ("centro-norte",)),
    ],
)
def test_nothing_personal(password, personal):
    assert _code(password, personal) == "password.personal"


def test_short_personal_words_are_ignored():
    ensure_acceptable("Ana-y-Leo-2024", personal=("Ana", "Leo"))
