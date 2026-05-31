"""Slug value object (tenant subdomain)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from medicore.domain.shared.errors import InvalidValueObject

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


@dataclass(frozen=True, slots=True)
class Slug:
    """A lowercase, URL-safe subdomain → ``<slug>.medicore.health``.

    Global uniqueness is enforced at the repository level, not here.
    """

    value: str

    def __post_init__(self) -> None:
        if not _SLUG_RE.match(self.value):
            raise InvalidValueObject(
                f"Slug must match ^[a-z0-9-]+$, got {self.value!r}"
            )
        if self.value.startswith("-") or self.value.endswith("-"):
            raise InvalidValueObject(f"Slug must not start or end with '-': {self.value!r}")

    def __str__(self) -> str:
        return self.value
