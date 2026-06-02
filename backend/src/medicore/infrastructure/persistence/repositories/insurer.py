"""SQLAlchemy InsurerRepository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.insurer import Insurer
from medicore.domain.shared.identifiers import InsurerId, TenantId
from medicore.infrastructure.persistence.mappers.entities import to_insurer
from medicore.infrastructure.persistence.models.insurer import InsurerModel


class SqlInsurerRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(InsurerModel).filter(InsurerModel.tenant_id == self._tid)

    def get_by_id(self, insurer_id: InsurerId) -> Insurer | None:
        row = self._q().filter(InsurerModel.id == insurer_id.value).first()
        return to_insurer(row) if row else None

    def list(self, active_only: bool = False) -> list[Insurer]:
        q = self._q()
        if active_only:
            q = q.filter(InsurerModel.active.is_(True))
        rows = q.order_by(InsurerModel.name).all()
        return [to_insurer(r) for r in rows]

    def save(self, insurer: Insurer) -> None:
        row = self._s.get(InsurerModel, insurer.id.value)
        if row is None:
            row = InsurerModel(id=insurer.id.value)
            self._s.add(row)
        row.tenant_id = insurer.tenant_id.value
        row.name = insurer.name
        row.phone = insurer.phone
        row.email = insurer.email
        row.address = insurer.address
        row.contact_person = insurer.contact_person
        row.notes = insurer.notes
        row.active = insurer.active
        row.created_at = insurer.created_at
        row.updated_at = insurer.updated_at
