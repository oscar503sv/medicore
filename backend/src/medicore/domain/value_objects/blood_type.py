"""BloodType value object."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.domain.shared.errors import InvalidValueObject

_VALID = frozenset({"O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"})


@dataclass(frozen=True, slots=True)
class BloodType:
    """An ABO/Rh blood group."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if normalized not in _VALID:
            raise InvalidValueObject(f"Invalid blood type: {self.value!r}")
        # frozen dataclass: bypass to store the normalized form
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
