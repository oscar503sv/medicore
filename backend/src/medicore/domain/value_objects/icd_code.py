"""IcdCode value object (ICD/CIE-10 and CIE-11 diagnosis)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from medicore.domain.shared.errors import InvalidValueObject

# Permissive pattern that accepts both CIE-10 ("I10", "E11.9", "S82.101A") and CIE-11
# stem/extension codes ("BA00", "1A00", "ND56.2", "XS8H"). The catalog is the source of
# truth for which codes actually exist; this only guards against obvious garbage input.
_ICD_RE = re.compile(r"^[A-Z0-9]{2,8}(?:\.[A-Z0-9]{1,5})?$")


@dataclass(frozen=True, slots=True)
class IcdCode:
    """An ICD/CIE diagnosis code with a human label."""

    code: str
    label: str

    def __post_init__(self) -> None:
        normalized = self.code.strip().upper()
        if not _ICD_RE.match(normalized):
            raise InvalidValueObject(f"Invalid diagnosis code: {self.code!r}")
        object.__setattr__(self, "code", normalized)
