"""Clinical notes: templates, section text, switching templates, clinic settings and the
template a consultation opens with."""

from __future__ import annotations

import pytest

from medicore.domain.enums import AppointmentType, NoteRole
from medicore.domain.services.note_templates import (
    HISTORY,
    NARRATIVE,
    PSOAP,
    SOAP,
    SYSTEM_TEMPLATES,
    resolve_template,
)
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.clinical_note import (
    ClinicalNote,
    NoteSectionSpec,
    NoteTemplate,
)
from medicore.domain.value_objects.note_settings import NoteSettings


def test_system_catalog():
    assert list(SYSTEM_TEMPLATES) == ["soap", "psoap", "history", "evolution", "narrative"]
    assert [s.key for s in PSOAP.sections] == [
        "problems", "subjective", "objective", "assessment", "plan"]
    # Every structured template has a plan, so prescriptions always get indications.
    for t in SYSTEM_TEMPLATES.values():
        assert t is NARRATIVE or any(s.role == NoteRole.PLAN for s in t.sections)


def test_template_invariants():
    with pytest.raises(InvalidValueObject):
        NoteTemplate("x", "X", ())
    dup = NoteSectionSpec("a", NoteRole.FREE, "A")
    with pytest.raises(InvalidValueObject):
        NoteTemplate("x", "X", (dup, dup))


def test_texts_and_completion():
    note = ClinicalNote.blank(SOAP)
    assert note.is_empty() and note.completion_ratio() == 0
    note = note.with_texts({"subjective": "Dolor", "plan": "Reposo"})
    assert note.completion_ratio() == 0.5
    assert note.missing_required() == ("objective", "assessment")
    assert note.text_for(NoteRole.PLAN) == "Reposo"
    with pytest.raises(InvalidValueObject) as err:
        note.with_texts({"nope": "x"})
    assert err.value.code == "note.unknown_section"
    with pytest.raises(InvalidValueObject):
        note.with_texts({"plan": "x" * 20_001})


def test_optional_sections_do_not_count():
    note = ClinicalNote.blank(HISTORY).with_texts(
        {"anamnesis": "a", "physical_exam": "b", "impression": "c", "treatment": "d"})
    assert note.completion_ratio() == 1 and note.missing_required() == ()


def test_switch_carries_text_by_role():
    soap = ClinicalNote.blank(SOAP).with_texts(
        {"subjective": "Tos", "objective": "Afebril", "assessment": "IRA", "plan": "Líquidos"})
    history = soap.switch_to(HISTORY)
    assert history.template == "history" and history.name == "Historia clínica completa"
    assert history.texts() == {"anamnesis": "Tos", "background": "", "physical_exam": "Afebril",
                               "impression": "IRA", "treatment": "Líquidos"}
    # Narrative has no SOAP roles: everything lands in its one section, under its title.
    narrative = soap.switch_to(NARRATIVE)
    assert narrative.texts()["narrative"] == (
        "Subjetivo:\nTos\n\nObjetivo:\nAfebril\n\nAnálisis:\nIRA\n\nPlan:\nLíquidos")
    # And back: nothing is lost, it goes into the first section.
    back = narrative.switch_to(SOAP)
    assert back.texts()["subjective"].startswith("Nota:\nSubjetivo:\nTos")
    # Problems have no place in SOAP: kept under their heading.
    psoap = ClinicalNote.blank(PSOAP).with_texts({"problems": "- HTA", "plan": "Control"})
    assert psoap.switch_to(SOAP).texts()["subjective"] == "Problemas:\n- HTA"


def test_prefill_only_blank_sections():
    note = ClinicalNote.blank(PSOAP).prefill(NoteRole.PROBLEMS, "- Asma")
    assert note.texts()["problems"] == "- Asma"
    assert note.prefill(NoteRole.PROBLEMS, "- Otra").texts()["problems"] == "- Asma"
    assert ClinicalNote.blank(SOAP).prefill(NoteRole.PROBLEMS, "- Asma").is_empty()


def test_settings_invariants():
    NoteSettings(enabled=("soap", "history"), default="soap", rules={"first_visit": "history"})
    with pytest.raises(InvalidValueObject) as err:
        NoteSettings(enabled=("history",), default="soap")
    assert err.value.code == "note.default_not_enabled"
    with pytest.raises(InvalidValueObject):
        NoteSettings(enabled=("soap",), rules={"follow_up": "evolution"})
    with pytest.raises(InvalidValueObject):
        NoteSettings(rules={"teleconsult": "soap"})
    assert NoteSettings().allows("narrative")


def _resolve(settings: NoteSettings, kind=AppointmentType.CONSULT, first=False, fav=None):
    return resolve_template(settings, appointment_type=kind, first_visit=first, favourite=fav)


def test_resolution_order():
    rules = NoteSettings(rules={"first_visit": "history", "follow_up": "evolution"})
    assert _resolve(rules, first=True, kind=AppointmentType.FOLLOW_UP) == "history"
    assert _resolve(rules, kind=AppointmentType.FOLLOW_UP, fav="narrative") == "evolution"
    assert _resolve(rules, fav="narrative") == "narrative"  # no rule: the doctor's favourite
    assert _resolve(rules) == "soap"
    # A locked format ignores the favourite; a favourite the clinic disabled is skipped.
    assert _resolve(NoteSettings(default="psoap", locked=True), fav="narrative") == "psoap"
    assert _resolve(NoteSettings(enabled=("soap",)), fav="narrative") == "soap"
    assert _resolve(NoteSettings(default="custom")) == "soap"  # unknown template: SOAP
