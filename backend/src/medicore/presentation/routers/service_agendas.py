"""Service agendas router (the vaccination room and the like). Listing is open to who books
appointments; mutations need organization.manage (enforced in the use cases)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.service_agendas import (
    CreateServiceAgenda,
    CreateServiceAgendaCommand,
    ListServiceAgendas,
    ServiceAgendaView,
    SetServiceAgendaActive,
    UpdateServiceAgenda,
)
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.shared.identifiers import LocationId, ServiceAgendaId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.service_agendas import (
    CreateServiceAgendaRequest,
    ServiceAgendaActiveRequest,
    ServiceAgendaResponse,
    UpdateServiceAgendaRequest,
)

router = APIRouter(prefix="/service-agendas", tags=["service-agendas"])


def _ser(agenda: ServiceAgenda, slot_minutes: int | None = None) -> dict:
    return {
        "id": str(agenda.id),
        "name": agenda.name,
        "kind": str(agenda.kind),
        "location_id": str(agenda.location_id) if agenda.location_id else None,
        "active": agenda.active,
        "slot_minutes": slot_minutes,
        "created_at": agenda.created_at,
        "updated_at": agenda.updated_at,
    }


def _ser_view(view: ServiceAgendaView) -> dict:
    return _ser(view.agenda, view.slot_minutes)


@router.get("", response_model=list[ServiceAgendaResponse])
def list_service_agendas(actor: Actor, uow: UoW, active_only: bool = Query(False)):
    with uow:
        views = ListServiceAgendas(uow).execute(actor, active_only=active_only)
    return [_ser_view(v) for v in views]


@router.post("", response_model=ServiceAgendaResponse, status_code=201)
def create_service_agenda(
    body: CreateServiceAgendaRequest, actor: Actor, uow: UoW, clock: Clock
):
    cmd = CreateServiceAgendaCommand(
        name=body.name,
        kind=body.kind,
        location_id=LocationId.parse(body.location_id) if body.location_id else None,
    )
    return _ser(CreateServiceAgenda(uow, clock).execute(actor, cmd))


@router.patch("/{agenda_id}", response_model=ServiceAgendaResponse)
def update_service_agenda(
    agenda_id: str, body: UpdateServiceAgendaRequest, actor: Actor, uow: UoW, clock: Clock
):
    agenda = UpdateServiceAgenda(uow, clock).execute(
        actor,
        ServiceAgendaId.parse(agenda_id),
        name=body.name,
        location_id=LocationId.parse(body.location_id) if body.location_id else None,
        clear_location="location_id" in body.model_fields_set and body.location_id is None,
    )
    return _ser(agenda)


@router.post("/{agenda_id}/active", response_model=ServiceAgendaResponse)
def set_service_agenda_active(
    agenda_id: str, body: ServiceAgendaActiveRequest, actor: Actor, uow: UoW, clock: Clock
):
    agenda = SetServiceAgendaActive(uow, clock).execute(
        actor, ServiceAgendaId.parse(agenda_id), body.active
    )
    return _ser(agenda)
