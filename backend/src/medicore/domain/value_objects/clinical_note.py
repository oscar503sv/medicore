"""Clinical note value objects: a note template and the note written with it.

A template is an ordered list of sections, each with a stable ``key``, a ``role`` (what the
section is for, see ``NoteRole``), a title and whether it must be filled for the note to
count as complete. A ``ClinicalNote`` is a snapshot of the template it was written with plus
the text of every section, so a signed record reads the same even if the template changes
or disappears later.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from medicore.domain.enums import NoteRole
from medicore.domain.shared.errors import InvalidValueObject

MAX_SECTION_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class NoteSectionSpec:
    key: str
    role: NoteRole
    title: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class NoteTemplate:
    key: str
    name: str
    sections: tuple[NoteSectionSpec, ...]
    system: bool = True  # built in; custom clinic templates are not

    def __post_init__(self) -> None:
        if not self.sections:
            raise InvalidValueObject("A note template needs at least one section")
        keys = [s.key for s in self.sections]
        if len(set(keys)) != len(keys):
            raise InvalidValueObject("Note template section keys must be unique")


@dataclass(frozen=True, slots=True)
class NoteSection:
    key: str
    role: NoteRole
    title: str
    required: bool
    text: str = ""

    @property
    def filled(self) -> bool:
        return bool(self.text.strip())


def _heading(section: NoteSection) -> str:
    return f"{section.title}:\n{section.text.strip()}"


@dataclass(frozen=True, slots=True)
class ClinicalNote:
    template: str  # the key of the template it was written with
    name: str  # that template's name, frozen with the note
    sections: tuple[NoteSection, ...]

    @classmethod
    def blank(cls, template: NoteTemplate) -> ClinicalNote:
        return cls(
            template=template.key,
            name=template.name,
            sections=tuple(
                NoteSection(key=s.key, role=s.role, title=s.title, required=s.required)
                for s in template.sections
            ),
        )

    # ── reading ──
    def text_for(self, role: NoteRole) -> str:
        """All the text written under ``role``, blank sections skipped."""
        return "\n\n".join(s.text.strip() for s in self.sections if s.role == role and s.filled)

    def texts(self) -> dict[str, str]:
        return {s.key: s.text for s in self.sections}

    def is_empty(self) -> bool:
        return not any(s.filled for s in self.sections)

    def missing_required(self) -> tuple[str, ...]:
        """Keys of the required sections still blank."""
        return tuple(s.key for s in self.sections if s.required and not s.filled)

    def completion_ratio(self) -> float:
        """Share of the required sections filled (any section when none is required)."""
        counted = [s for s in self.sections if s.required] or list(self.sections)
        return sum(s.filled for s in counted) / len(counted)

    # ── writing ──
    def with_texts(self, texts: dict[str, str]) -> ClinicalNote:
        """A copy with the given sections rewritten; unknown keys are refused."""
        known = {s.key for s in self.sections}
        unknown = sorted(set(texts) - known)
        if unknown:
            raise InvalidValueObject(
                f"Unknown note sections: {', '.join(unknown)}", code="note.unknown_section",
                sections=", ".join(unknown),
            )
        for key, text in texts.items():
            if len(text) > MAX_SECTION_CHARS:
                raise InvalidValueObject(
                    f"Note section {key} is too long", code="note.section_too_long",
                    max=MAX_SECTION_CHARS,
                )
        return replace(self, sections=tuple(
            replace(s, text=texts[s.key]) if s.key in texts else s for s in self.sections
        ))

    def prefill(self, role: NoteRole, text: str) -> ClinicalNote:
        """Write ``text`` into the first blank section with ``role``, if there is one."""
        target = next((s for s in self.sections if s.role == role and not s.filled), None)
        if target is None or not text.strip():
            return self
        return self.with_texts({target.key: text})

    def switch_to(self, template: NoteTemplate) -> ClinicalNote:
        """The same note in another template. Text follows its role; text whose role the
        new template lacks goes, under its old title, into the free-text section (or the
        first section) so nothing written is ever lost."""
        target = ClinicalNote.blank(template)
        roles = {s.role for s in target.sections}
        texts: dict[str, list[str]] = {s.key: [] for s in target.sections}
        first_by_role: dict[NoteRole, str] = {}
        for s in target.sections:
            first_by_role.setdefault(s.role, s.key)
        catch_all = first_by_role.get(NoteRole.FREE, target.sections[0].key)
        for old in self.sections:
            if not old.filled:
                continue
            if old.role in roles:
                texts[first_by_role[old.role]].append(old.text.strip())
            else:
                texts[catch_all].append(_heading(old))
        return target.with_texts({k: "\n\n".join(v) for k, v in texts.items() if v})
