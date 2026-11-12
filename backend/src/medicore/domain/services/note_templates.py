"""The built-in clinical note templates and the rule that picks one for a consultation.

Titles are stored in Spanish (the clinic's language); the interface translates the
sections of built-in templates by their key.
"""

from __future__ import annotations

from collections.abc import Collection

from medicore.domain.enums import AppointmentType, NoteRole
from medicore.domain.value_objects.clinical_note import NoteSectionSpec, NoteTemplate
from medicore.domain.value_objects.note_settings import DEFAULT_TEMPLATE, FIRST_VISIT, NoteSettings

_S = NoteSectionSpec

SOAP = NoteTemplate("soap", "SOAP", (
    _S("subjective", NoteRole.SUBJECTIVE, "Subjetivo"),
    _S("objective", NoteRole.OBJECTIVE, "Objetivo"),
    _S("assessment", NoteRole.ASSESSMENT, "Análisis"),
    _S("plan", NoteRole.PLAN, "Plan"),
))
# Problem-oriented SOAP: the patient's active problems first (ISSS audit criterion).
PSOAP = NoteTemplate("psoap", "P-SOAP", (
    _S("problems", NoteRole.PROBLEMS, "Problemas"),
    *SOAP.sections,
))
HISTORY = NoteTemplate("history", "Historia clínica completa", (
    _S("anamnesis", NoteRole.SUBJECTIVE, "Motivo de consulta y enfermedad actual"),
    _S("background", NoteRole.HISTORY, "Antecedentes", required=False),
    _S("physical_exam", NoteRole.OBJECTIVE, "Examen físico"),
    _S("impression", NoteRole.ASSESSMENT, "Impresión diagnóstica"),
    _S("treatment", NoteRole.PLAN, "Plan de tratamiento"),
))
EVOLUTION = NoteTemplate("evolution", "Nota de evolución", (
    _S("evolution", NoteRole.SUBJECTIVE, "Evolución"),
    _S("findings", NoteRole.OBJECTIVE, "Hallazgos"),
    _S("analysis", NoteRole.ASSESSMENT, "Análisis"),
    _S("conduct", NoteRole.PLAN, "Conducta"),
))
NARRATIVE = NoteTemplate("narrative", "Nota narrativa", (
    _S("narrative", NoteRole.FREE, "Nota"),
))

SYSTEM_TEMPLATES: dict[str, NoteTemplate] = {
    t.key: t for t in (SOAP, PSOAP, HISTORY, EVOLUTION, NARRATIVE)
}


def resolve_template(
    settings: NoteSettings,
    *,
    appointment_type: AppointmentType,
    first_visit: bool,
    favourite: str | None,
    available: Collection[str] = SYSTEM_TEMPLATES.keys(),
) -> str:
    """The template a new consultation opens with: the clinic's first-visit rule, then its
    rule for the appointment type, then (unless the format is locked) the doctor's
    favourite, then the clinic default. ``available`` are the templates that exist."""
    candidates = [
        settings.rules.get(FIRST_VISIT) if first_visit else None,
        settings.rules.get(str(appointment_type)),
        None if settings.locked else favourite,
        settings.default,
    ]
    for key in candidates:
        if key and key in available and settings.allows(key):
            return key
    return DEFAULT_TEMPLATE
