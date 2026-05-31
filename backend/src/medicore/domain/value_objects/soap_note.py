"""SoapNote value object — the SOAP clinical note (Subjective/Objective/Assessment/Plan)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SoapNote:
    """A SOAP note. Each section is free text; empty sections are allowed in drafts."""

    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""

    def filled_sections(self) -> int:
        sections = (self.subjective, self.objective, self.assessment, self.plan)
        return sum(bool(s.strip()) for s in sections)

    def is_complete(self) -> bool:
        """All four sections have content."""
        return self.filled_sections() == 4
