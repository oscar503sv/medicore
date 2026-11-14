"""AES-GCM sealing of secrets at rest."""

from __future__ import annotations

import base64

import pytest

from medicore.infrastructure.auth.secret_box import AesGcmSecretBox

KEY = bytes(range(32))


def test_round_trip():
    box = AesGcmSecretBox(KEY)
    sealed = box.seal("JBSWY3DPEHPK3PXP")
    assert sealed.startswith("v1.") and "JBSWY3DPEHPK3PXP" not in sealed
    assert box.open(sealed) == "JBSWY3DPEHPK3PXP"


def test_same_plaintext_seals_to_different_values():
    box = AesGcmSecretBox(KEY)
    assert box.seal("secret") != box.seal("secret")


def test_tampered_value_is_rejected():
    box = AesGcmSecretBox(KEY)
    body = base64.urlsafe_b64decode(box.seal("secret").removeprefix("v1.") + "==")
    flipped = bytes([body[0] ^ 1]) + body[1:]
    with pytest.raises(ValueError):
        box.open("v1." + base64.urlsafe_b64encode(flipped).decode().rstrip("="))


def test_wrong_key_is_rejected():
    sealed = AesGcmSecretBox(KEY).seal("secret")
    with pytest.raises(ValueError):
        AesGcmSecretBox(bytes(32)).open(sealed)


@pytest.mark.parametrize(
    "sealed", ["", "v1.", "v1.AAAA", "v2.AAAAAAAAAAAAAAAAAAAAAAAA", "plain", "v1.***"]
)
def test_malformed_values_are_rejected(sealed):
    with pytest.raises(ValueError):
        AesGcmSecretBox(KEY).open(sealed)


def test_key_must_be_32_bytes():
    with pytest.raises(ValueError):
        AesGcmSecretBox(b"short")
