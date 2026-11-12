"""CustomNoteTemplate aggregate — a clinical note template built by the clinic.

Clinics on plans with custom note templates add their own next to the built-in ones. A
template is a name and an ordered list of sections, each with a title, a role (what it is
for, so text follows it when switching templates and the plan feeds prescriptions) and
whether it must be filled. Notes snapshot the template they were written with, so editing
or archiving a template never changes a signed record or a consultation in progress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import NoteRole
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import NoteTemplateId, TenantId, UserId
from medicore.domain.value_objects.clinical_note import NoteSectionSpec, NoteTemplate

MAX_NAME = 80
MAX_SECTIONS = 12
MAX_TITLE = 80


@dataclass(frozen=True, slots=True)
class SectionDraft:
    """A section as the clinic writes it; its key is assigned by position."""

    title: str
    role: NoteRole
    required: bool = True


def _sections(drafts: list[SectionDraft]) -> tuple[NoteSectionSpec, ...]:
    if not drafts:
        raise InvalidValueObject("A note template needs a section", code="note.no_sections")
    if len(drafts) > MAX_SECTIONS:
        raise InvalidValueObject(
            "Too many sections", code="note.too_many_sections", max=MAX_SECTIONS
        )
    specs = []
    for i, d in enumerate(drafts, start=1):
        title = d.title.strip()
        if not title or len(title) > MAX_TITLE:
            raise InvalidValueObject(
                "Section titles are 1 to 80 characters", code="note.invalid_title",
                max=MAX_TITLE,
            )
        specs.append(NoteSectionSpec(key=f"s{i}", role=d.role, title=title, required=d.required))
    return tuple(specs)


def _name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise InvalidValueObject(
            "Template names are 1 to 80 characters", code="note.invalid_name", max=MAX_NAME
        )
    return name


@dataclass(slots=True)
class CustomNoteTemplate:
    id: NoteTemplateId
    tenant_id: TenantId
    name: str
    sections: tuple[NoteSectionSpec, ...]
    created_by_id: UserId
    archived: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls, *, tenant_id: TenantId, name: str, sections: list[SectionDraft],
        created_by_id: UserId, now: datetime,
    ) -> CustomNoteTemplate:
        return cls(
            id=NoteTemplateId.new(), tenant_id=tenant_id, name=_name(name),
            sections=_sections(sections), created_by_id=created_by_id, created_at=now,
            updated_at=now,
        )

    @property
    def key(self) -> str:
        return str(self.id)

    def revise(self, *, name: str, sections: list[SectionDraft], now: datetime) -> None:
        self.name = _name(name)
        self.sections = _sections(sections)
        self.updated_at = now

    def archive(self, now: datetime) -> None:
        self.archived = True
        self.updated_at = now

    def to_template(self) -> NoteTemplate:
        return NoteTemplate(key=self.key, name=self.name, sections=self.sections, system=False)
