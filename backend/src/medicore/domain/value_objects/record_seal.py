"""RecordSeal value object: the SHA-256 digest that seals a signed record, and the version of
the canonical form it was computed from (so the form can evolve without breaking old seals)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from medicore.domain.shared.errors import InvalidValueObject

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
FINGERPRINT_LENGTH = 16


@dataclass(frozen=True, slots=True)
class RecordSeal:
    version: int
    digest: str  # 64 lowercase hex characters

    def __post_init__(self) -> None:
        if self.version < 1:
            raise InvalidValueObject("a seal version starts at 1", code="record.seal_invalid")
        if not _DIGEST_RE.match(self.digest):
            raise InvalidValueObject(
                "a seal digest is 64 lowercase hex characters", code="record.seal_invalid"
            )

    @property
    def fingerprint(self) -> str:
        """The short form shown on paper and screens."""
        return self.digest[:FINGERPRINT_LENGTH]
