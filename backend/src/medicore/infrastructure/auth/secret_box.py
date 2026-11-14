"""AES-256-GCM sealing of secrets at rest.

Sealed format: ``"v1." + base64url(nonce(12) || ciphertext+tag)``. The version prefix leaves
room to rotate the algorithm or key later without guessing what a stored value is.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = "v1."
_NONCE_BYTES = 12
_KEY_BYTES = 32


class AesGcmSecretBox:
    def __init__(self, key: bytes) -> None:
        if len(key) != _KEY_BYTES:
            raise ValueError(f"the encryption key must be {_KEY_BYTES} bytes")
        self._aead = AESGCM(key)

    def seal(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        blob = nonce + self._aead.encrypt(nonce, plaintext.encode(), None)
        return _VERSION + base64.urlsafe_b64encode(blob).decode().rstrip("=")

    def open(self, sealed: str) -> str:
        if not sealed.startswith(_VERSION):
            raise ValueError("unknown sealed secret format")
        body = sealed.removeprefix(_VERSION)
        try:
            blob = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        except (binascii.Error, ValueError) as exc:
            raise ValueError("malformed sealed secret") from exc
        if len(blob) <= _NONCE_BYTES:
            raise ValueError("malformed sealed secret")
        try:
            return self._aead.decrypt(blob[:_NONCE_BYTES], blob[_NONCE_BYTES:], None).decode()
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise ValueError("sealed secret is corrupt or the key is wrong") from exc
