"""ServiceAgendaRepository port — the clinic's service agendas (vaccination room, ...)."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.shared.identifiers import ServiceAgendaId


class ServiceAgendaRepository(Protocol):
    def get_by_id(self, agenda_id: ServiceAgendaId) -> ServiceAgenda | None: ...

    def list(self, active_only: bool = False) -> list[ServiceAgenda]:
        """By name."""
        ...

    def name_exists(self, name: str, exclude: ServiceAgendaId | None = None) -> bool:
        """Whether another agenda of the clinic has this name (case-insensitive)."""
        ...

    def save(self, agenda: ServiceAgenda) -> None: ...
