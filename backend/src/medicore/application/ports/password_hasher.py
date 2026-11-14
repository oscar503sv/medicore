"""PasswordHasher port — abstracts password hashing/verification."""

from __future__ import annotations

from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...

    def verify(self, plain: str, hashed: str) -> bool: ...

    def dummy_verify(self, plain: str) -> None:
        """Spend the same work as ``verify`` against a hash that never matches.

        Called when there is no account to check, so the response time does not reveal
        whether it exists.
        """
        ...
