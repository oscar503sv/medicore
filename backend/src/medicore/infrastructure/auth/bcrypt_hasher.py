"""bcrypt-backed PasswordHasher (uses the bcrypt library directly).

We call ``bcrypt`` directly rather than through passlib because passlib 1.7.x is
incompatible with bcrypt 5.x. bcrypt rejects secrets longer than 72 bytes, so we
truncate defensively (the standard bcrypt behavior).
"""

from __future__ import annotations

import bcrypt

_MAX_BYTES = 72


def _prepare(plain: str) -> bytes:
    return plain.encode("utf-8")[:_MAX_BYTES]


class BcryptPasswordHasher:
    def hash(self, plain: str) -> str:
        return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")

    def verify(self, plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False
