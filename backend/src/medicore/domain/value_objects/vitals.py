"""Vitals value object."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from decimal import Decimal

from medicore.domain.shared.errors import InvalidValueObject

_BP_RE = re.compile(r"^\d{2,3}/\d{2,3}$")


@dataclass(frozen=True, slots=True)
class Vitals:
    """A snapshot of clinical vital signs. All fields optional; an empty Vitals is valid."""

    blood_pressure: str | None = None  # "120/80"
    heart_rate: int | None = None  # bpm
    spo2: int | None = None  # %
    temperature: Decimal | None = None  # °C
    weight: Decimal | None = None  # kg
    glucose: int | None = None  # mg/dL
    height: Decimal | None = None  # cm
    fetal_heart_rate: int | None = None  # bpm (obstetric)

    def __post_init__(self) -> None:
        if self.blood_pressure is not None and not _BP_RE.match(self.blood_pressure):
            raise InvalidValueObject(
                f"blood_pressure must look like '120/80', got {self.blood_pressure!r}",
                code="vitals.invalid_blood_pressure",
            )
        if self.spo2 is not None and not (0 <= self.spo2 <= 100):
            raise InvalidValueObject(
                f"spo2 must be 0..100, got {self.spo2}", code="vitals.spo2_out_of_range"
            )
        for name in ("heart_rate", "glucose", "fetal_heart_rate"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise InvalidValueObject(
                    f"{name} must be non-negative, got {v}", code="vitals.negative", field=name
                )
        for name in ("temperature", "weight", "height"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise InvalidValueObject(
                    f"{name} must be non-negative, got {v}", code="vitals.negative", field=name
                )

    def bmi(self) -> Decimal | None:
        """Body mass index (kg/m²), or None if weight or height is missing."""
        if self.weight is None or self.height is None or self.height == 0:
            return None
        height_m = self.height / Decimal(100)
        return (self.weight / (height_m * height_m)).quantize(Decimal("0.1"))

    def is_empty(self) -> bool:
        return all(getattr(self, f) is None for f in VITAL_FIELDS)

    def filled_fields(self) -> tuple[str, ...]:
        """Names of the readings taken (never their values)."""
        return tuple(n for n in VITAL_FIELDS if getattr(self, n) is not None)

    def with_changes(self, changes: Mapping[str, object]) -> Vitals:
        """A copy with only the given fields replaced (None clears one), revalidated."""
        unknown = sorted(set(changes) - set(VITAL_FIELDS))
        if unknown:
            raise InvalidValueObject(
                "unknown vitals: " + ", ".join(unknown), code="vitals.unknown_field"
            )
        return replace(self, **changes)  # type: ignore[arg-type]

    def changed_fields(self, other: Vitals) -> tuple[str, ...]:
        return tuple(n for n in VITAL_FIELDS if getattr(self, n) != getattr(other, n))


VITAL_FIELDS = tuple(f.name for f in fields(Vitals))
