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
from medicore.domain.shared.identifiers import ExceptionId, ServiceAgendaId, UserId
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


def _weekly(body: list[WeeklyDayRequest]) -> list[WeeklyDay]:
    return [
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


def _exception(body: ExceptionRequest) -> AvailabilityException:
    return AvailabilityException(
        id=ExceptionId.new(),
        date=body.date,
        kind=body.kind,
        reason=body.reason,
        blocks=[
            TimeRange(time(*map(int, b.start.split(":"))), time(*map(int, b.end.split(":"))))
            for b in body.blocks
        ],
    )


def _rules(body: BookingRulesRequest) -> BookingRules:
    return BookingRules(
        slot_minutes=body.slot_minutes,
        min_advance_hours=body.min_advance_hours,
        allow_same_day=body.allow_same_day,
    )


@router.get("/me", response_model=AvailabilityResponse)
def get_my_availability(actor: Actor, uow: UoW):
    with uow:
        av = GetMyAvailability(uow).execute(actor)
    return ser_availability(av)


@router.put("/me/weekly", response_model=AvailabilityResponse)
def update_weekly(body: list[WeeklyDayRequest], actor: Actor, uow: UoW, clock: Clock):
    av = UpdateWeeklySchedule(uow, clock).execute(actor, _weekly(body))
    return ser_availability(av)


@router.post("/me/exceptions", response_model=AvailabilityResponse)
def add_exception(body: ExceptionRequest, actor: Actor, uow: UoW, clock: Clock):
    av = AddAvailabilityException(uow, clock).execute(actor, _exception(body))
    return ser_availability(av)


@router.delete("/me/exceptions/{exception_id}", response_model=AvailabilityResponse)
def remove_exception(exception_id: str, actor: Actor, uow: UoW, clock: Clock):
    av = RemoveAvailabilityException(uow, clock).execute(
        actor, ExceptionId.parse(exception_id)
    )
    return ser_availability(av)


@router.put("/me/rules", response_model=AvailabilityResponse)
def update_rules(body: BookingRulesRequest, actor: Actor, uow: UoW, clock: Clock):
    av = UpdateBookingRules(uow, clock).execute(actor, _rules(body))
    return ser_availability(av)


# A service agenda's schedule: the same editor, addressed by agenda and gated by
# organization.manage instead of availability.manage.
@router.get("/agendas/{agenda_id}", response_model=AvailabilityResponse)
def get_agenda_availability(agenda_id: str, actor: Actor, uow: UoW):
    with uow:
        av = GetMyAvailability(uow).execute(actor, ServiceAgendaId.parse(agenda_id))
    return ser_availability(av)


@router.put("/agendas/{agenda_id}/weekly", response_model=AvailabilityResponse)
def update_agenda_weekly(
    agenda_id: str, body: list[WeeklyDayRequest], actor: Actor, uow: UoW, clock: Clock
):
    av = UpdateWeeklySchedule(uow, clock).execute(
        actor, _weekly(body), ServiceAgendaId.parse(agenda_id)
    )
    return ser_availability(av)


@router.post("/agendas/{agenda_id}/exceptions", response_model=AvailabilityResponse)
def add_agenda_exception(
    agenda_id: str, body: ExceptionRequest, actor: Actor, uow: UoW, clock: Clock
):
    av = AddAvailabilityException(uow, clock).execute(
        actor, _exception(body), ServiceAgendaId.parse(agenda_id)
    )
    return ser_availability(av)


@router.delete(
    "/agendas/{agenda_id}/exceptions/{exception_id}", response_model=AvailabilityResponse
)
def remove_agenda_exception(
    agenda_id: str, exception_id: str, actor: Actor, uow: UoW, clock: Clock
):
    av = RemoveAvailabilityException(uow, clock).execute(
        actor, ExceptionId.parse(exception_id), ServiceAgendaId.parse(agenda_id)
    )
    return ser_availability(av)


@router.put("/agendas/{agenda_id}/rules", response_model=AvailabilityResponse)
def update_agenda_rules(
    agenda_id: str, body: BookingRulesRequest, actor: Actor, uow: UoW, clock: Clock
):
    av = UpdateBookingRules(uow, clock).execute(
        actor, _rules(body), ServiceAgendaId.parse(agenda_id)
    )
    return ser_availability(av)


@router.get("/preview", response_model=PreviewResponse)
def preview(
    actor: Actor,
    uow: UoW,
    clock: Clock,
    week_start: date = Query(...),
    doctor_id: str | None = Query(None),
    agenda_id: str | None = Query(None),
):
    with uow:
        did = UserId.parse(doctor_id) if doctor_id else None
        aid = ServiceAgendaId.parse(agenda_id) if agenda_id else None
        preview_data = PreviewAvailability(uow, clock).execute(actor, week_start, did, aid)
    return PreviewResponse(
        preview={
            d.isoformat(): [ser_slot(s) for s in slots]
            for d, slots in preview_data.items()
        }
    )
