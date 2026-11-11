"""Quotas a subscription grants: plan defaults and per-clinic custom overrides."""

from __future__ import annotations

from dataclasses import dataclass, fields

from medicore.domain.shared.errors import InvalidValueObject


@dataclass(frozen=True, slots=True)
class PlanLimits:
    """Seat, site and storage quotas. ``None`` means unlimited (sized per contract).

    Doctors and support staff (nursing, reception, extra admins) are separate quotas; the
    clinic's first admin account never counts. Only active users count.
    """

    doctors: int | None = None
    support_users: int | None = None
    locations: int | None = None
    storage_gb: int | None = None

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if value is not None and value < 0:
                raise InvalidValueObject(f"{f.name} cannot be negative", code="plan.invalid_limit")

    def overridden_by(self, overrides: LimitOverrides | None) -> PlanLimits:
        """These limits with every override that is set taking precedence."""
        if overrides is None:
            return self
        return PlanLimits(
            **{
                f.name: getattr(overrides, f.name)
                if getattr(overrides, f.name) is not None
                else getattr(self, f.name)
                for f in fields(self)
            }
        )


@dataclass(frozen=True, slots=True)
class LimitOverrides:
    """Per-clinic exceptions to the plan's quotas. ``None`` means "use the plan's"."""

    doctors: int | None = None
    support_users: int | None = None
    locations: int | None = None
    storage_gb: int | None = None

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if value is not None and value < 0:
                raise InvalidValueObject(f"{f.name} cannot be negative", code="plan.invalid_limit")

    @property
    def is_empty(self) -> bool:
        return all(getattr(self, f.name) is None for f in fields(self))
