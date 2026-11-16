"""SQLAlchemy ServiceAgendaRepository."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from medicore.application.common.errors import ConflictError
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.shared.identifiers import ServiceAgendaId, TenantId
from medicore.infrastructure.persistence.mappers.entities import to_service_agenda
from medicore.infrastructure.persistence.models.service_agenda import ServiceAgendaModel

NAME_INDEX = "uq_service_agendas_tenant_name"


class SqlServiceAgendaRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(ServiceAgendaModel).filter(ServiceAgendaModel.tenant_id == self._tid)

    def get_by_id(self, agenda_id: ServiceAgendaId) -> ServiceAgenda | None:
        row = self._q().filter(ServiceAgendaModel.id == agenda_id.value).first()
        return to_service_agenda(row) if row else None

    def list(self, active_only: bool = False) -> list[ServiceAgenda]:
        q = self._q()
        if active_only:
            q = q.filter(ServiceAgendaModel.active.is_(True))
        return [to_service_agenda(r) for r in q.order_by(ServiceAgendaModel.name).all()]

    def name_exists(self, name: str, exclude: ServiceAgendaId | None = None) -> bool:
        q = self._q().filter(func.lower(ServiceAgendaModel.name) == name.casefold())
        if exclude is not None:
            q = q.filter(ServiceAgendaModel.id != exclude.value)
        return q.first() is not None

    def save(self, agenda: ServiceAgenda) -> None:
        row = self._s.get(ServiceAgendaModel, agenda.id.value)
        if row is None:
            row = ServiceAgendaModel(id=agenda.id.value)
            self._s.add(row)
        row.tenant_id = agenda.tenant_id.value
        row.name = agenda.name
        row.kind = str(agenda.kind)
        row.location_id = agenda.location_id.value if agenda.location_id else None
        row.active = agenda.active
        row.created_at = agenda.created_at
        row.updated_at = agenda.updated_at
        # Flushed here so a name taken between the check and the write (two admins at once)
        # surfaces as the same conflict the check raises, not as a bare database error.
        try:
            self._s.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "diag", None) and exc.orig.diag.constraint_name == NAME_INDEX:
                raise ConflictError(
                    "a service agenda with that name exists",
                    code="service_agenda.name_taken", name=agenda.name,
                ) from exc
            raise
