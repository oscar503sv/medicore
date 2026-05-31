"""IcdCode value object (ICD-10 / CIE-10 diagnosis)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from medicore.domain.shared.errors import InvalidValueObject

# ICD-10: a letter, two digits, optionally a dot and up to four more alphanumerics.
# e.g. "I10", "E11.9", "S82.101A"
_ICD10_RE = re.compile(r"^[A-TV-Z]\d{2}(?:\.[A-Z0-9]{1,4})?$")


@dataclass(frozen=True, slots=True)
class IcdCode:
    """An ICD-10 diagnosis code with a human label."""

    code: str
    label: str

    def __post_init__(self) -> None:
        normalized = self.code.strip().upper()
        if not _ICD10_RE.match(normalized):
            raise InvalidValueObject(f"Invalid ICD-10 code: {self.code!r}")
        object.__setattr__(self, "code", normalized)
