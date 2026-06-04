"""Doctor availability use cases."""

from __future__ import annotations

from datetime import date, timedelta

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import ensure_can_manage_availability
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.services.slot_resolver import Slot, resolve_available_slots
from medicore.domain.shared.identifiers import AvailabilityId, ExceptionId, UserId


class GetMyAvailability:
    """Return the actor's availability, creating an (unsaved) empty default if none exists."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> DoctorAvailability:
        ensure_can_manage_availability(actor)
        existing = self._uow.availability.get_by_doctor(actor.user_id)
        if existing is not None:
            return existing
        return DoctorAvailability(
            id=AvailabilityId.new(), tenant_id=actor.tenant_id, doctor_id=actor.user_id
        )


class _AvailabilityMutator:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _load_or_create(self, actor: ActorContext) -> DoctorAvailability:
        existing = self._uow.availability.get_by_doctor(actor.user_id)
        if existing is not None:
            return existing
        return DoctorAvailability(
            id=AvailabilityId.new(), tenant_id=actor.tenant_id, doctor_id=actor.user_id
        )

    def _persist(self, actor: ActorContext, availability: DoctorAvailability) -> None:
        doctor = self._uow.users.get_by_id(availability.doctor_id)
        with self._uow:
            self._uow.availability.save(availability)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "availability.updated", "DoctorAvailability",
                    str(availability.id),
                    subject=subject(doctor.name) if doctor else None,
                )
            )
            self._uow.commit()


class UpdateWeeklySchedule(_AvailabilityMutator):
    def execute(
        self, actor: ActorContext, weekly: list[WeeklyDay]
    ) -> DoctorAvailability:
        ensure_can_manage_availability(actor)
        availability = self._load_or_create(actor)
        for day in weekly:
            availability.set_day(day)
        self._persist(actor, availability)
        return availability


class AddAvailabilityException(_AvailabilityMutator):
    def execute(
        self, actor: ActorContext, exception: AvailabilityException
    ) -> DoctorAvailability:
        ensure_can_manage_availability(actor)
        availability = self._load_or_create(actor)
        availability.add_exception(exception)
        self._persist(actor, availability)
        return availability


class RemoveAvailabilityException(_AvailabilityMutator):
    def execute(
        self, actor: ActorContext, exception_id: ExceptionId
    ) -> DoctorAvailability:
        ensure_can_manage_availability(actor)
        availability = self._load_or_create(actor)
        availability.remove_exception(exception_id)
        self._persist(actor, availability)
        return availability


class UpdateBookingRules(_AvailabilityMutator):
    def execute(self, actor: ActorContext, rules: BookingRules) -> DoctorAvailability:
        ensure_can_manage_availability(actor)
        availability = self._load_or_create(actor)
        availability.update_rules(rules)
        self._persist(actor, availability)
        return availability


class PreviewAvailability:
    """Resolve the week's slots (available/taken/out-of-hours) for the actor's schedule."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, week_start: date, doctor_id: UserId | None = None
    ) -> dict[date, list[Slot]]:
        ensure_can_manage_availability(actor)
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
