"""ExamRequest value object — one lab, imaging or other exam ordered in a consultation."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.domain.enums import ExamKind
from medicore.domain.shared.errors import InvalidValueObject

EXAM_NAME_MAX = 200
EXAM_NOTES_MAX = 500


@dataclass(frozen=True, slots=True)
class ExamRequest:
    name: str  # "Hemograma completo", "Ultrasonografía pélvica"
    kind: ExamKind = ExamKind.LAB
    notes: str | None = None  # "en ayunas", "transvaginal"…

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > EXAM_NAME_MAX:
            raise InvalidValueObject("an exam needs a name", code="exam.invalid_name",
                                     max=EXAM_NAME_MAX)
        notes = (self.notes or "").strip() or None
        if notes and len(notes) > EXAM_NOTES_MAX:
            raise InvalidValueObject("exam notes are too long", code="exam.notes_too_long",
                                     max=EXAM_NOTES_MAX)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "notes", notes)
