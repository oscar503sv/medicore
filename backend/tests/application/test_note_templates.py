"""Clinical note templates: the template a consultation opens with, switching it, the
clinic's settings, the doctor's favourite and amendments."""

from __future__ import annotations

from dataclasses import replace

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.consultations import (
    AutosaveConsultation,
    ChangeNoteTemplate,
    ConsultationPatch,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.application.use_cases.note_templates import (
    GetNoteCatalog,
    SetFavouriteNoteTemplate,
    UpdateNoteSettings,
)
from medicore.application.use_cases.records import AmendMedicalRecord
from medicore.domain.services.plan_catalog import INDEPENDIENTE
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.note_settings import NoteSettings
from tests.application.test_consultations import booked, fill
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator


def _clinic(settings: NoteSettings | None = None):
    seed = seed_clinic()
    if settings is not None:
        seed.tenant.note_settings = settings
    return seed, seed.factory.for_tenant(seed.tenant.id)


def _start(seed, uow):
    return StartConsultation(uow, FixedClock()).execute(seed.doctor_actor, booked(seed, uow).id)


def test_first_visit_rule_then_type_rule():
    seed, uow = _clinic(NoteSettings(rules={"first_visit": "history", "consult": "evolution"}))
    first = _start(seed, uow)
    assert first.note.template == "history"
    assert first.note.name == "Historia clínica completa"
    fill_history = {"anamnesis": "a", "physical_exam": "b", "impression": "c", "treatment": "d"}
    AutosaveConsultation(uow, FixedClock()).execute(
        seed.doctor_actor, first.id, ConsultationPatch(note=fill_history))
    SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, SignConsultationCommand(consultation_id=first.id))
    # The patient now has a record: the next visit is not a first visit.
    assert _start(seed, uow).note.template == "evolution"


def test_favourite_applies_without_rule_and_never_when_locked():
    seed, uow = _clinic()
    seed.doctor.set_note_template("narrative")
    assert _start(seed, uow).note.template == "narrative"

    seed, uow = _clinic(NoteSettings(enabled=("psoap",), default="psoap", locked=True))
    seed.doctor.set_note_template("narrative")
    seed.patient.tags = ["Hipertensión", "Diabetes tipo 2"]
    note = _start(seed, uow).note
    assert note.template == "psoap"
    assert note.texts()["problems"] == "- Hipertensión\n- Diabetes tipo 2"


def test_change_template_carries_text():
    seed, uow = _clinic()
    seed.patient.tags = ["Asma"]
    consultation = _start(seed, uow)
    AutosaveConsultation(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id, ConsultationPatch(note={"subjective": "Tos seca"}))
    changed = ChangeNoteTemplate(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id, "psoap")
    assert changed.note.texts()["subjective"] == "Tos seca"
    assert changed.note.texts()["problems"] == "- Asma"  # prefilled on the way in
    assert uow.consultations.get_by_id(consultation.id).note.template == "psoap"
    with pytest.raises(ValidationError) as err:
        ChangeNoteTemplate(uow, FixedClock()).execute(seed.doctor_actor, consultation.id, "dap")
    assert err.value.code == "note.unknown_template"


def test_change_template_respects_the_clinic():
    seed, uow = _clinic(NoteSettings(enabled=("soap", "history"), default="soap"))
    consultation = _start(seed, uow)
    with pytest.raises(ValidationError) as err:
        ChangeNoteTemplate(uow, FixedClock()).execute(
            seed.doctor_actor, consultation.id, "narrative")
    assert err.value.code == "note.template_not_enabled"

    seed.tenant.note_settings = replace(seed.tenant.note_settings, locked=True)
    with pytest.raises(PermissionDenied) as denied:
        ChangeNoteTemplate(uow, FixedClock()).execute(
            seed.doctor_actor, consultation.id, "history")
    assert denied.value.code == "note.template_locked"
    # Re-selecting the current template is harmless.
    ChangeNoteTemplate(uow, FixedClock()).execute(seed.doctor_actor, consultation.id, "soap")


def test_settings_by_admin_are_audited():
    seed, uow = _clinic()
    settings = NoteSettings(enabled=("soap", "history"), default="soap",
                            rules={"first_visit": "history"}, locked=True)
    catalog = UpdateNoteSettings(uow, FixedClock()).execute(seed.actor(seed.admin), settings)
    assert catalog.settings == settings and catalog.allowed == ("soap", "history")
    assert uow.tenants.get_by_id(seed.tenant.id).note_settings == settings
    [entry] = uow.audit.query(action="organization.note_settings_updated")
    assert entry.metadata["after"]["rules"] == {"first_visit": "history"}


def test_only_the_admin_or_a_solo_doctor_configures():
    seed, uow = _clinic()
    with pytest.raises(PermissionDenied) as err:
        UpdateNoteSettings(uow, FixedClock()).execute(seed.doctor_actor, NoteSettings())
    assert err.value.code == "note.cannot_configure"
    assert GetNoteCatalog(uow).execute(seed.doctor_actor).can_configure is False

    tenant = uow.tenants.get_by_id(seed.tenant.id)
    tenant.subscription = replace(tenant.subscription, plan_code=INDEPENDIENTE)
    assert GetNoteCatalog(uow).execute(seed.doctor_actor).can_configure is True
    UpdateNoteSettings(uow, FixedClock()).execute(seed.doctor_actor, NoteSettings(default="psoap"))
    assert uow.tenants.get_by_id(seed.tenant.id).note_settings.default == "psoap"


def test_favourite():
    seed, uow = _clinic()
    catalog = SetFavouriteNoteTemplate(uow).execute(seed.doctor_actor, "evolution")
    assert catalog.favourite == "evolution"
    assert uow.users.get_by_id(seed.doctor.id).preferences.note_template == "evolution"
    assert SetFavouriteNoteTemplate(uow).execute(seed.doctor_actor, None).favourite is None
    with pytest.raises(ValidationError):
        SetFavouriteNoteTemplate(uow).execute(seed.doctor_actor, "nope")


def test_amend_rewrites_sections_of_the_signed_template():
    seed, uow = _clinic()
    consultation = _start(seed, uow)
    fill(seed, uow, consultation)
    record = SignConsultation(uow, SequentialCodeGenerator(), FixedClock()).execute(
        seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id))
    amended = AmendMedicalRecord(uow, FixedClock()).execute(
        seed.doctor_actor, record.id, note={"plan": "plan corregido"})
    assert amended.note.texts()["plan"] == "plan corregido"
    assert amended.note.texts()["subjective"] == "subjetivo"
    assert record.note.texts()["plan"] == "plan"  # the original is untouched
