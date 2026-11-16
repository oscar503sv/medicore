"""Availability use cases: a doctor edits their own schedule; a service agenda's schedule is
edited by whoever manages the organization."""

from __future__ import annotations

from datetime import date, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.services.slot_resolver import Slot, resolve_available_slots
from medicore.domain.shared.identifiers import (
    AvailabilityId,
    ExceptionId,
    ServiceAgendaId,
    UserId,
)


def _agenda_to_edit(
    uow: UnitOfWork, actor: ActorContext, agenda_id: ServiceAgendaId | None
) -> ServiceAgenda | None:
    """Check who may edit the schedule: the actor's own (None) or a service agenda's."""
    if agenda_id is None:
        ensure_permission(actor, Permission.AVAILABILITY_MANAGE)
        return None
    ensure_permission(actor, Permission.ORGANIZATION_MANAGE)
    agenda = uow.service_agendas.get_by_id(agenda_id)
    if agenda is None:
        raise EntityNotFound("ServiceAgenda", agenda_id)
    return agenda


def _existing_or_empty(
    uow: UnitOfWork, actor: ActorContext, agenda: ServiceAgenda | None
) -> DoctorAvailability:
    existing = (
        uow.availability.get_by_agenda(agenda.id)
        if agenda is not None
        else uow.availability.get_by_doctor(actor.user_id)
    )
    if existing is not None:
        return existing
    return DoctorAvailability(
        id=AvailabilityId.new(),
        tenant_id=actor.tenant_id,
        doctor_id=None if agenda is not None else actor.user_id,
        agenda_id=agenda.id if agenda is not None else None,
    )


class GetMyAvailability:
    """Return the actor's availability (or a service agenda's), creating an (unsaved) empty
    default if none exists."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, agenda_id: ServiceAgendaId | None = None
    ) -> DoctorAvailability:
        agenda = _agenda_to_edit(self._uow, actor, agenda_id)
        return _existing_or_empty(self._uow, actor, agenda)


class _AvailabilityMutator:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _load_or_create(
        self, actor: ActorContext, agenda_id: ServiceAgendaId | None
    ) -> DoctorAvailability:
        agenda = _agenda_to_edit(self._uow, actor, agenda_id)
        return _existing_or_empty(self._uow, actor, agenda)

    def _persist(self, actor: ActorContext, availability: DoctorAvailability) -> None:
        name = None
        if availability.agenda_id is not None:
            agenda = self._uow.service_agendas.get_by_id(availability.agenda_id)
            name = agenda.name if agenda else None
        elif availability.doctor_id is not None:
            doctor = self._uow.users.get_by_id(availability.doctor_id)
            name = doctor.name if doctor else None
        with self._uow:
            self._uow.availability.save(availability)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "availability.updated", "DoctorAvailability",
                    str(availability.id),
                    subject=subject(name) if name else None,
                )
            )
            self._uow.commit()


class UpdateWeeklySchedule(_AvailabilityMutator):
    def execute(
        self,
        actor: ActorContext,
        weekly: list[WeeklyDay],
        agenda_id: ServiceAgendaId | None = None,
    ) -> DoctorAvailability:
        availability = self._load_or_create(actor, agenda_id)
        for day in weekly:
            availability.set_day(day)
        self._persist(actor, availability)
        return availability


class AddAvailabilityException(_AvailabilityMutator):
    def execute(
        self,
        actor: ActorContext,
        exception: AvailabilityException,
        agenda_id: ServiceAgendaId | None = None,
    ) -> DoctorAvailability:
        availability = self._load_or_create(actor, agenda_id)
        availability.add_exception(exception)
        self._persist(actor, availability)
        return availability


class RemoveAvailabilityException(_AvailabilityMutator):
    def execute(
        self,
        actor: ActorContext,
        exception_id: ExceptionId,
        agenda_id: ServiceAgendaId | None = None,
    ) -> DoctorAvailability:
        availability = self._load_or_create(actor, agenda_id)
        availability.remove_exception(exception_id)
        self._persist(actor, availability)
        return availability


class UpdateBookingRules(_AvailabilityMutator):
    def execute(
        self,
        actor: ActorContext,
        rules: BookingRules,
        agenda_id: ServiceAgendaId | None = None,
    ) -> DoctorAvailability:
        availability = self._load_or_create(actor, agenda_id)
        availability.update_rules(rules)
        self._persist(actor, availability)
        return availability


class PreviewAvailability:
    """Resolve the week's slots (available/taken/out-of-hours) for the actor's schedule."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self,
        actor: ActorContext,
        week_start: date,
        doctor_id: UserId | None = None,
        agenda_id: ServiceAgendaId | None = None,
    ) -> dict[date, list[Slot]]:
        agenda = _agenda_to_edit(self._uow, actor, agenda_id)
        if agenda is not None:
            availability = self._uow.availability.get_by_agenda(agenda.id)
            target: UserId | ServiceAgendaId = agenda.id
        else:
            target = doctor_id or actor.user_id
            availability = self._uow.availability.get_by_doctor(target)
        if availability is None:
            raise EntityNotFound("DoctorAvailability", target)
        return {
            (day := week_start + timedelta(days=offset)): resolve_available_slots(
                availability, day, now=self._clock.now()
            )
            for offset in range(7)
        }
