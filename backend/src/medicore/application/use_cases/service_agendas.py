"""Service agendas: schedules of a clinic service (the vaccination room) that no single
doctor owns. Managing them is an organization task; anyone who books appointments lists them.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ConflictError, EntityNotFound, ValidationError
from medicore.application.common.permissions import (
    Permission,
    ensure_permission,
    has_permission,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.enums import ServiceAgendaKind
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import LocationId, ServiceAgendaId


@dataclass(frozen=True, slots=True)
class ServiceAgendaView:
    agenda: ServiceAgenda
    slot_minutes: int | None  # None → no availability configured yet


@dataclass(frozen=True, slots=True)
class CreateServiceAgendaCommand:
    name: str
    kind: ServiceAgendaKind
    location_id: LocationId | None = None


def _check_location(uow: UnitOfWork, actor: ActorContext, location_id: LocationId | None) -> None:
    if location_id is None:
        return
    tenant = uow.tenants.get_by_id(actor.tenant_id)
    if tenant is None or all(loc.id != location_id for loc in tenant.locations):
        raise ValidationError("unknown location", code="service_agenda.invalid_location")


def _ensure_name_free(
    uow: UnitOfWork, name: str, exclude: ServiceAgendaId | None = None
) -> None:
    if uow.service_agendas.name_exists(name, exclude):
        raise ConflictError(
            "a service agenda with that name exists",
            code="service_agenda.name_taken", name=name,
        )


def _require(uow: UnitOfWork, agenda_id: ServiceAgendaId) -> ServiceAgenda:
    agenda = uow.service_agendas.get_by_id(agenda_id)
    if agenda is None:
        raise EntityNotFound("ServiceAgenda", agenda_id)
    return agenda


class ListServiceAgendas:
    """The clinic's agendas. Open to who manages the organization and to who books
    appointments (they pick the agenda)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, active_only: bool = False) -> list[ServiceAgendaView]:
        if not has_permission(actor, Permission.ORGANIZATION_MANAGE):
            ensure_permission(actor, Permission.APPOINTMENTS_VIEW)
        agendas = self._uow.service_agendas.list(active_only=active_only)
        schedules = self._uow.availability.list_for_agendas([a.id for a in agendas])
        return [
            ServiceAgendaView(
                a, schedules[a.id].rules.slot_minutes if a.id in schedules else None
            )
            for a in agendas
        ]


class CreateServiceAgenda:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: CreateServiceAgendaCommand) -> ServiceAgenda:
        ensure_permission(actor, Permission.ORGANIZATION_MANAGE)
        now = self._clock.now()
        agenda = ServiceAgenda(
            id=ServiceAgendaId.new(), tenant_id=actor.tenant_id, name=cmd.name, kind=cmd.kind,
            location_id=cmd.location_id, created_at=now, updated_at=now,
        )
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        if not tenant.subscription.has_module(agenda.module):
            raise PermissionDenied(
                "the module of this agenda is not contracted",
                code="service_agenda.module_required", module=str(agenda.module),
            )
        with self._uow:
            _check_location(self._uow, actor, cmd.location_id)
            _ensure_name_free(self._uow, agenda.name)
            self._uow.service_agendas.save(agenda)
            self._uow.audit.append(audit_entry(
                actor, now, "service_agenda.created", "ServiceAgenda", str(agenda.id),
                subject=subject(agenda.name), kind=str(agenda.kind),
            ))
            self._uow.commit()
        return agenda


class UpdateServiceAgenda:
    """Rename an agenda and/or change its default location (``clear_location`` removes it)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self,
        actor: ActorContext,
        agenda_id: ServiceAgendaId,
        *,
        name: str | None = None,
        location_id: LocationId | None = None,
        clear_location: bool = False,
    ) -> ServiceAgenda:
        ensure_permission(actor, Permission.ORGANIZATION_MANAGE)
        with self._uow:
            agenda = _require(self._uow, agenda_id)
            now = self._clock.now()
            if name is not None:
                agenda.rename(name, now)
                _ensure_name_free(self._uow, agenda.name, exclude=agenda.id)
            if location_id is not None or clear_location:
                new_location = None if clear_location else location_id
                _check_location(self._uow, actor, new_location)
                agenda.set_location(new_location, now)
            self._uow.service_agendas.save(agenda)
            self._uow.audit.append(audit_entry(
                actor, now, "service_agenda.updated", "ServiceAgenda", str(agenda.id),
                subject=subject(agenda.name),
            ))
            self._uow.commit()
        return agenda


class SetServiceAgendaActive:
    """Archive or reactivate an agenda. Its past appointments stay; it takes no new ones."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, agenda_id: ServiceAgendaId, active: bool
    ) -> ServiceAgenda:
        ensure_permission(actor, Permission.ORGANIZATION_MANAGE)
        with self._uow:
            agenda = _require(self._uow, agenda_id)
            now = self._clock.now()
            agenda.set_active(active, now)
            self._uow.service_agendas.save(agenda)
            self._uow.audit.append(audit_entry(
                actor, now, "service_agenda.activated" if active else "service_agenda.archived",
                "ServiceAgenda", str(agenda.id), subject=subject(agenda.name),
            ))
            self._uow.commit()
        return agenda
