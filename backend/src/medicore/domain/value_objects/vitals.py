"""Vitals value object."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
                f"blood_pressure must look like '120/80', got {self.blood_pressure!r}"
            )
        if self.spo2 is not None and not (0 <= self.spo2 <= 100):
            raise InvalidValueObject(f"spo2 must be 0..100, got {self.spo2}")
        for name in ("heart_rate", "glucose", "fetal_heart_rate"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise InvalidValueObject(f"{name} must be non-negative, got {v}")
        for name in ("temperature", "weight", "height"):
            v = getattr(self, name)
            if v is not None and v < 0:
                raise InvalidValueObject(f"{name} must be non-negative, got {v}")

    def bmi(self) -> Decimal | None:
        """Body mass index (kg/m²), or None if weight or height is missing."""
        if self.weight is None or self.height is None or self.height == 0:
            return None
        height_m = self.height / Decimal(100)
        return (self.weight / (height_m * height_m)).quantize(Decimal("0.1"))

    def is_empty(self) -> bool:
        return all(
            getattr(self, f) is None
            for f in (
                "blood_pressure",
                "heart_rate",
                "spo2",
                "temperature",
                "weight",
                "glucose",
                "height",
                "fetal_heart_rate",
            )
        )
