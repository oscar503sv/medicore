"""bcrypt-backed PasswordHasher (uses the bcrypt library directly).

We call ``bcrypt`` directly rather than through passlib because passlib 1.7.x is
incompatible with bcrypt 5.x. bcrypt rejects secrets longer than 72 bytes, so we
truncate defensively (the standard bcrypt behavior).
"""

from __future__ import annotations

import functools

import bcrypt

_MAX_BYTES = 72
_ROUNDS = 12
_DUMMY_SECRET = b"medicore.invalid-user.dummy"


def _prepare(plain: str) -> bytes:
    return plain.encode("utf-8")[:_MAX_BYTES]


@functools.cache
def _dummy_hash() -> bytes:
    # Computed once per process (use cases are built per request), with the same cost
    # as real hashes so a dummy check takes as long as a real one.
    return bcrypt.hashpw(_DUMMY_SECRET, bcrypt.gensalt(_ROUNDS))


class BcryptPasswordHasher:
    def hash(self, plain: str) -> str:
        return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt(_ROUNDS)).decode("utf-8")

    def verify(self, plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    def dummy_verify(self, plain: str) -> None:
        bcrypt.checkpw(_prepare(plain), _dummy_hash())
