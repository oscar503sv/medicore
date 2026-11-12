"""SQLAlchemy NoteTemplateRepository (the clinic's custom note templates)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.note_template import CustomNoteTemplate
from medicore.domain.enums import NoteRole
from medicore.domain.shared.identifiers import NoteTemplateId, TenantId, UserId
from medicore.domain.value_objects.clinical_note import NoteSectionSpec
from medicore.infrastructure.persistence.models.note_template import NoteTemplateModel

_ROLES = {r.value: r for r in NoteRole}


def _to_entity(row: NoteTemplateModel) -> CustomNoteTemplate:
    return CustomNoteTemplate(
        id=NoteTemplateId.parse(row.id),
        tenant_id=TenantId.parse(row.tenant_id),
        name=row.name,
        sections=tuple(
            NoteSectionSpec(key=s["key"], role=_ROLES.get(s.get("role", ""), NoteRole.FREE),
                            title=s.get("title", ""), required=bool(s.get("required", False)))
            for s in row.sections or []
        ),
        created_by_id=UserId.parse(row.created_by_id),
        archived=row.archived,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlNoteTemplateRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(NoteTemplateModel).filter(NoteTemplateModel.tenant_id == self._tid)

    def get_by_id(self, template_id: NoteTemplateId) -> CustomNoteTemplate | None:
        row = self._q().filter(NoteTemplateModel.id == template_id.value).first()
        return _to_entity(row) if row else None

    def list(self, include_archived: bool = False) -> list[CustomNoteTemplate]:
        q = self._q()
        if not include_archived:
            q = q.filter(NoteTemplateModel.archived.is_(False))
        return [_to_entity(r) for r in q.order_by(NoteTemplateModel.created_at).all()]

    def save(self, template: CustomNoteTemplate) -> None:
        row = self._s.get(NoteTemplateModel, template.id.value)
        if row is None:
            row = NoteTemplateModel(id=template.id.value)
            self._s.add(row)
        row.tenant_id = template.tenant_id.value
        row.name = template.name
        row.sections = [
            {"key": s.key, "role": str(s.role), "title": s.title, "required": s.required}
            for s in template.sections
        ]
        row.created_by_id = template.created_by_id.value
        row.archived = template.archived
        row.created_at = template.created_at
        row.updated_at = template.updated_at
