"""Custom note templates (Clínica Plus and up): building, editing and archiving them, using
them in a consultation, and what happens without the plan feature."""

from __future__ import annotations

from dataclasses import replace

import pytest

from medicore.application.common.errors import EntityNotFound
from medicore.application.use_cases.consultations import (
    AutosaveConsultation,
    ChangeNoteTemplate,
    ConsultationPatch,
)
from medicore.application.use_cases.note_templates import (
    ArchiveNoteTemplate,
    CreateNoteTemplate,
    GetNoteCatalog,
    UpdateNoteSettings,
    UpdateNoteTemplate,
    available_templates,
)
from medicore.domain.entities.note_template import SectionDraft
from medicore.domain.enums import AppointmentType, NoteRole
from medicore.domain.services.note_templates import resolve_template
from medicore.domain.services.plan_catalog import CLINICA, INDEPENDIENTE
from medicore.domain.shared.errors import InvalidValueObject, PermissionDenied
from medicore.domain.shared.identifiers import NoteTemplateId
from medicore.domain.value_objects.note_settings import NoteSettings
from tests.application.test_note_templates import _start
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock

PEDIATRIC = [
    SectionDraft("Motivo de consulta", NoteRole.SUBJECTIVE),
    SectionDraft("Desarrollo y crecimiento", NoteRole.OBJECTIVE),
    SectionDraft("Vacunas pendientes", NoteRole.FREE, required=False),
    SectionDraft("Indicaciones", NoteRole.PLAN),
]


def _clinic(plan: str | None = None):
    seed = seed_clinic()  # Empresarial: custom templates included
    if plan:
        seed.tenant.subscription = replace(seed.tenant.subscription, plan_code=plan)
    return seed, seed.factory.for_tenant(seed.tenant.id)


def _create(seed, uow, sections=PEDIATRIC):
    catalog = CreateNoteTemplate(uow, FixedClock()).execute(
        seed.actor(seed.admin), "Control pediátrico", sections)
    return next(t for t in catalog.templates if not t.system), catalog


def test_create_and_use_in_a_consultation():
    seed, uow = _clinic()
    template, catalog = _create(seed, uow)
    assert catalog.custom_allowed and template.key in catalog.allowed
    assert [(s.key, s.title, s.required) for s in template.sections] == [
        ("s1", "Motivo de consulta", True), ("s2", "Desarrollo y crecimiento", True),
        ("s3", "Vacunas pendientes", False), ("s4", "Indicaciones", True)]
    assert uow.audit.query(action="note_template.created")

    consultation = _start(seed, uow)
    AutosaveConsultation(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id,
        ConsultationPatch(note={"subjective": "Fiebre", "plan": "Paracetamol"}))
    changed = ChangeNoteTemplate(uow, FixedClock()).execute(
        seed.doctor_actor, consultation.id, template.key)
    assert changed.note.name == "Control pediátrico"
    assert changed.note.texts() == {"s1": "Fiebre", "s2": "", "s3": "", "s4": "Paracetamol"}
    assert changed.note.text_for(NoteRole.PLAN) == "Paracetamol"  # feeds prescriptions

    # A rule can open consultations with it.
    UpdateNoteSettings(uow, FixedClock()).execute(
        seed.actor(seed.admin), NoteSettings(rules={"consult": template.key}))
    settings = uow.tenants.get_by_id(seed.tenant.id).note_settings
    assert resolve_template(settings, appointment_type=AppointmentType.CONSULT,
                            first_visit=False, favourite=None,
                            available=available_templates(uow)) == template.key


def test_edit_keeps_written_notes():
    seed, uow = _clinic()
    template, _ = _create(seed, uow)
    consultation = _start(seed, uow)
    ChangeNoteTemplate(uow, FixedClock()).execute(seed.doctor_actor, consultation.id, template.key)
    catalog = UpdateNoteTemplate(uow, FixedClock()).execute(
        seed.actor(seed.admin), NoteTemplateId.parse(template.key), "Control del niño sano",
        [SectionDraft("Motivo", NoteRole.SUBJECTIVE), SectionDraft("Plan", NoteRole.PLAN)])
    [edited] = [t for t in catalog.templates if not t.system]
    assert edited.name == "Control del niño sano" and len(edited.sections) == 2
    # The consultation in progress keeps the version it was written with.
    assert len(uow.consultations.get_by_id(consultation.id).note.sections) == 4


def test_archive_scrubs_settings():
    seed, uow = _clinic()
    template, _ = _create(seed, uow)
    UpdateNoteSettings(uow, FixedClock()).execute(seed.actor(seed.admin), NoteSettings(
        enabled=("soap", template.key), default=template.key,
        rules={"follow_up": template.key}))
    catalog = ArchiveNoteTemplate(uow, FixedClock()).execute(
        seed.actor(seed.admin), NoteTemplateId.parse(template.key))
    assert template.key not in [t.key for t in catalog.templates]
    assert catalog.settings == NoteSettings(enabled=("soap",), default="soap")
    with pytest.raises(EntityNotFound):
        ArchiveNoteTemplate(uow, FixedClock()).execute(
            seed.actor(seed.admin), NoteTemplateId.parse(template.key))


def test_validation():
    seed, uow = _clinic()
    with pytest.raises(InvalidValueObject) as err:
        _create(seed, uow, [])
    assert err.value.code == "note.no_sections"
    with pytest.raises(InvalidValueObject):
        _create(seed, uow, [SectionDraft("  ", NoteRole.FREE)])
    with pytest.raises(InvalidValueObject):
        _create(seed, uow, [SectionDraft("x", NoteRole.FREE)] * 13)


def test_needs_the_plan_and_the_configurer():
    seed, uow = _clinic(CLINICA)
    assert GetNoteCatalog(uow).execute(seed.actor(seed.admin)).custom_allowed is False
    with pytest.raises(PermissionDenied) as err:
        _create(seed, uow)
    assert err.value.code == "plan.feature_required"

    seed, uow = _clinic()
    with pytest.raises(PermissionDenied) as denied:
        CreateNoteTemplate(uow, FixedClock()).execute(seed.doctor_actor, "X", PEDIATRIC)
    assert denied.value.code == "note.cannot_configure"


def test_templates_disappear_after_a_downgrade():
    seed, uow = _clinic()
    template, _ = _create(seed, uow)
    UpdateNoteSettings(uow, FixedClock()).execute(
        seed.actor(seed.admin), NoteSettings(default=template.key))
    tenant = uow.tenants.get_by_id(seed.tenant.id)
    tenant.subscription = replace(tenant.subscription, plan_code=INDEPENDIENTE)
    catalog = GetNoteCatalog(uow).execute(seed.actor(seed.admin))
    assert all(t.system for t in catalog.templates)
    assert catalog.settings.default == "soap"  # shown without the missing template
    assert _start(seed, uow).note.template == "soap"
