"""Mappers for DoctorAvailability and AvailabilityException."""

from __future__ import annotations

from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.enums import AvailabilityExceptionKind
from medicore.domain.shared.identifiers import AvailabilityId, ExceptionId, TenantId, UserId
from medicore.infrastructure.persistence.mappers._json import (
    dict_to_time_range,
    time_range_to_dict,
)
from medicore.infrastructure.persistence.models.availability import (
    AvailabilityExceptionModel,
    DoctorAvailabilityModel,
)


def _weekly_from_json(lst: list[dict]) -> list[WeeklyDay]:
    days = []
    for d in lst:
        blocks = [dict_to_time_range(b) for b in d.get("blocks", [])]
        days.append(
            WeeklyDay(day_of_week=d["day_of_week"], enabled=d.get("enabled", False), blocks=blocks)
        )
    return days


def _rules_from_json(d: dict) -> BookingRules:
    if not d:
        return BookingRules()
    return BookingRules(
        slot_minutes=d.get("slot_minutes", 30),
        buffer_minutes=d.get("buffer_minutes", 0),
        min_advance_hours=d.get("min_advance_hours", 0),
        max_advance_days=d.get("max_advance_days", 90),
        allow_same_day=d.get("allow_same_day", True),
    )


def to_availability_exception(row: AvailabilityExceptionModel) -> AvailabilityException:
    return AvailabilityException(
        id=ExceptionId.parse(row.id),
        date=row.date,
        kind=AvailabilityExceptionKind(row.kind),
        reason=row.reason or "",
        blocks=[dict_to_time_range(b) for b in (row.blocks or [])],
    )


def to_doctor_availability(
    row: DoctorAvailabilityModel,
    exceptions: list[AvailabilityExceptionModel],
) -> DoctorAvailability:
    return DoctorAvailability(
        id=AvailabilityId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        doctor_id=UserId.parse(row.doctor_id),
        weekly=_weekly_from_json(row.weekly or []),
        exceptions=[to_availability_exception(e) for e in exceptions],
        rules=_rules_from_json(row.rules or {}),
    )


def from_doctor_availability(av: DoctorAvailability) -> tuple[dict, list[dict]]:
    """Serialize a DoctorAvailability to (availability_dict, [exception_dict, ...])."""
    weekly = [
        {
            "day_of_week": d.day_of_week,
            "enabled": d.enabled,
            "blocks": [time_range_to_dict(b) for b in d.blocks],
        }
        for d in av.weekly
    ]
    rules = {
        "slot_minutes": av.rules.slot_minutes,
        "buffer_minutes": av.rules.buffer_minutes,
        "min_advance_hours": av.rules.min_advance_hours,
        "max_advance_days": av.rules.max_advance_days,
        "allow_same_day": av.rules.allow_same_day,
    }
    av_dict = {
        "id": av.id.value,
        "tenant_id": av.tenant_id.value,
        "doctor_id": av.doctor_id.value,
        "weekly": weekly,
        "rules": rules,
    }
    ex_dicts = [
        {
            "id": ex.id.value,
            "availability_id": av.id.value,
            "date": ex.date,
            "kind": str(ex.kind),
            "reason": ex.reason,
            "blocks": [time_range_to_dict(b) for b in ex.blocks],
        }
        for ex in av.exceptions
    ]
    return av_dict, ex_dicts
