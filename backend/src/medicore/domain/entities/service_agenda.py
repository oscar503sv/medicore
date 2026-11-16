"""ServiceAgenda: a clinic service with its own schedule, not tied to a doctor.

A vaccination room is attended by whichever nurse is on duty, so its appointments belong to
the service and not to a user. It takes one patient at a time, like a doctor's agenda; its
hours and slot length live in a ``DoctorAvailability`` that points at the agenda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import AddonModule, AppointmentType, ServiceAgendaKind
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import LocationId, ServiceAgendaId, TenantId

MAX_NAME_LENGTH = 80

_ACCEPTED_TYPES: dict[ServiceAgendaKind, frozenset[AppointmentType]] = {
    ServiceAgendaKind.VACCINATION: frozenset({AppointmentType.VACCINATION}),
}
_MODULES: dict[ServiceAgendaKind, AddonModule] = {
    ServiceAgendaKind.VACCINATION: AddonModule.VACCINATION,
}


@dataclass(slots=True)
class ServiceAgenda:
    id: ServiceAgendaId
    tenant_id: TenantId
    name: str
    kind: ServiceAgendaKind
    location_id: LocationId | None = None
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.name = _clean_name(self.name)

    @property
    def module(self) -> AddonModule:
        """The module the clinic must have contracted to use this agenda."""
        return _MODULES[self.kind]

    def accepts(self, kind: AppointmentType) -> bool:
        return kind in _ACCEPTED_TYPES[self.kind]

    def ensure_accepts(self, kind: AppointmentType) -> None:
        if not self.accepts(kind):
            raise DomainError(
                f"a {self.kind} agenda does not take {kind} appointments",
                code="appointment.type_not_for_agenda", type=str(kind),
            )

    def rename(self, name: str, now: datetime) -> None:
        self.name = _clean_name(name)
        self.updated_at = now

    def set_location(self, location_id: LocationId | None, now: datetime) -> None:
        self.location_id = location_id
        self.updated_at = now

    def set_active(self, active: bool, now: datetime) -> None:
        self.active = active
        self.updated_at = now


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidValueObject(
            "the service agenda needs a name", code="service_agenda.name_required"
        )
    if len(cleaned) > MAX_NAME_LENGTH:
        raise InvalidValueObject(
            "the service agenda name is too long", code="service_agenda.name_too_long",
            max=MAX_NAME_LENGTH,
        )
    return cleaned
