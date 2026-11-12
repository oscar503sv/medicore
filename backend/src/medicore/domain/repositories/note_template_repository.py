"""NoteTemplateRepository port — the clinic's custom note templates."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.note_template import CustomNoteTemplate
from medicore.domain.shared.identifiers import NoteTemplateId


class NoteTemplateRepository(Protocol):
    def get_by_id(self, template_id: NoteTemplateId) -> CustomNoteTemplate | None: ...

    def list(self, include_archived: bool = False) -> list[CustomNoteTemplate]:
        """Oldest first."""
        ...

    def save(self, template: CustomNoteTemplate) -> None: ...
