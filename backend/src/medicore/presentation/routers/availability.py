"""Doctor availability router."""

from __future__ import annotations

from datetime import date, time

from fastapi import APIRouter, Query

from medicore.application.use_cases.availability import (
    AddAvailabilityException,
    GetMyAvailability,
    PreviewAvailability,
    RemoveAvailabilityException,
    UpdateBookingRules,
    UpdateWeeklySchedule,
)
from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    WeeklyDay,
)
from medicore.domain.enums import AvailabilityExceptionKind
from medicore.domain.shared.identifiers import ExceptionId, UserId
from medicore.domain.value_objects.time_range import TimeRange
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.availability import (
    AvailabilityResponse,
    BookingRulesRequest,
    ExceptionRequest,
    PreviewResponse,
    WeeklyDayRequest,
)
from medicore.presentation.serializers import ser_availability, ser_slot

router = APIRouter(prefix="/availability", tags=["availability"])


@router.get("/me", response_model=AvailabilityResponse)
def get_my_availability(actor: Actor, uow: UoW):
    with uow:
        av = GetMyAvailability(uow).execute(actor)
    return ser_availability(av)


@router.put("/me/weekly", response_model=AvailabilityResponse)
def update_weekly(body: list[WeeklyDayRequest], actor: Actor, uow: UoW, clock: Clock):
    weekly = [
        WeeklyDay(
            day_of_week=d.day_of_week,
            enabled=d.enabled,
            blocks=[
                TimeRange(time(*map(int, b.start.split(":"))), time(*map(int, b.end.split(":"))))
                for b in d.blocks
            ],
        )
        for d in body
    ]
    av = UpdateWeeklySchedule(uow, clock).execute(actor, weekly)
    return ser_availability(av)


@router.post("/me/exceptions", response_model=AvailabilityResponse)
def add_exception(body: ExceptionRequest, actor: Actor, uow: UoW, clock: Clock):
    ex = AvailabilityException(
        id=ExceptionId.new(),
        date=body.date,
        kind=AvailabilityExceptionKind(body.kind),
        reason=body.reason,
        blocks=[
            TimeRange(time(*map(int, b.start.split(":"))), time(*map(int, b.end.split(":"))))
            for b in body.blocks
        ],
    )
    av = AddAvailabilityException(uow, clock).execute(actor, ex)
    return ser_availability(av)


@router.delete("/me/exceptions/{exception_id}", response_model=AvailabilityResponse)
def remove_exception(exception_id: str, actor: Actor, uow: UoW, clock: Clock):
    av = RemoveAvailabilityException(uow, clock).execute(
        actor, ExceptionId.parse(exception_id)
    )
    return ser_availability(av)


@router.put("/me/rules", response_model=AvailabilityResponse)
def update_rules(body: BookingRulesRequest, actor: Actor, uow: UoW, clock: Clock):
    rules = BookingRules(
        slot_minutes=body.slot_minutes,
        min_advance_hours=body.min_advance_hours,
        allow_same_day=body.allow_same_day,
    )
    av = UpdateBookingRules(uow, clock).execute(actor, rules)
    return ser_availability(av)


@router.get("/preview", response_model=PreviewResponse)
def preview(
    actor: Actor,
    uow: UoW,
    clock: Clock,
    week_start: date = Query(...),
    doctor_id: str | None = Query(None),
):
    with uow:
        did = UserId.parse(doctor_id) if doctor_id else None
        preview_data = PreviewAvailability(uow, clock).execute(actor, week_start, did)
    return PreviewResponse(
        preview={
            d.isoformat(): [ser_slot(s) for s in slots]
            for d, slots in preview_data.items()
        }
    )
