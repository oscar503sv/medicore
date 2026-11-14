"""SecretBox port — reversible encryption of small secrets stored in the database."""

from __future__ import annotations

from typing import Protocol


class SecretBox(Protocol):
    def seal(self, plaintext: str) -> str: ...

    def open(self, sealed: str) -> str:
        """Raises ``ValueError`` when the value is malformed or was tampered with."""
        ...
