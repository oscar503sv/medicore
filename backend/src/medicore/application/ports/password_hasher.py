"""PasswordHasher port — abstracts password hashing/verification."""

from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...

    def verify(self, plain: str, hashed: str) -> bool: ...
