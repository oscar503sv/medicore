"""bcrypt-backed PasswordHasher."""

from __future__ import annotations

from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class BcryptPasswordHasher:
    def hash(self, plain: str) -> str:
        return _ctx.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        return _ctx.verify(plain, hashed)
