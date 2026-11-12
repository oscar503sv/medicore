"""Clinical note templates: the catalog a clinic can use, its settings, each doctor's
favourite and the clinic's own templates.

The clinic admin decides which templates are enabled, the default, a template per
appointment type (and for a patient's first visit) and whether the format is mandatory. In
a single-doctor plan there is no admin to ask, so the doctor decides. Doctors keep a
favourite template, used when the clinic sets no rule for the visit. Plans with custom
note templates (Clínica Plus and up) let whoever configures the notes build their own.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.entitlements import has_feature
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import Permission, has_permission
from medicore.application.common.quotas import effective_limits
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.note_template import CustomNoteTemplate, SectionDraft
from medicore.domain.entities.tenant import Tenant
from medicore.domain.enums import NoteRole, PlanFeature, Role
from medicore.domain.services.note_templates import SYSTEM_TEMPLATES
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import NoteTemplateId
from medicore.domain.value_objects.clinical_note import ClinicalNote, NoteTemplate
from medicore.domain.value_objects.note_settings import NoteSettings


@dataclass(frozen=True, slots=True)
class NoteCatalog:
    templates: tuple[NoteTemplate, ...]  # every template the clinic has
    settings: NoteSettings
    favourite: str | None  # the actor's own
    can_configure: bool
    custom_allowed: bool  # the plan includes custom templates

    @property
    def allowed(self) -> tuple[str, ...]:
        return tuple(t.key for t in self.templates if self.settings.allows(t.key))


def custom_allowed(uow: UnitOfWork, tenant: Tenant | None = None) -> bool:
    tenant = tenant or uow.tenants.get_by_id(uow.tenant_id)
    return tenant is not None and has_feature(uow, tenant, PlanFeature.CUSTOM_NOTE_TEMPLATES)


def available_templates(uow: UnitOfWork) -> dict[str, NoteTemplate]:
    """The templates a clinic can use: the built-in ones, then its own (archived ones and,
    on a plan without custom templates, all of them left out)."""
    templates = dict(SYSTEM_TEMPLATES)
    if custom_allowed(uow):
        templates.update((t.key, t.to_template()) for t in uow.note_templates.list())
    return templates


def find_template(uow: UnitOfWork, key: str) -> NoteTemplate:
    template = available_templates(uow).get(key)
    if template is None:
        raise ValidationError(f"Unknown note template {key}", code="note.unknown_template")
    return template


def problems_prefill(note: ClinicalNote, tags: list[str]) -> ClinicalNote:
    """A problem-oriented note starts from the patient's known conditions."""
    return note.prefill(NoteRole.PROBLEMS, "\n".join(f"- {t}" for t in tags))


def can_configure_notes(uow: UnitOfWork, actor: ActorContext, tenant: Tenant) -> bool:
    if has_permission(actor, Permission.ORGANIZATION_MANAGE):
        return True
    return actor.role == Role.DOCTOR and effective_limits(uow, tenant).doctors == 1


def _tenant(uow: UnitOfWork, actor: ActorContext) -> Tenant:
    tenant = uow.tenants.get_by_id(actor.tenant_id)
    if tenant is None:
        raise EntityNotFound("Tenant", actor.tenant_id)
    return tenant


def _catalog(uow: UnitOfWork, actor: ActorContext, tenant: Tenant) -> NoteCatalog:
    user = uow.users.get_by_id(actor.user_id)
    templates = available_templates(uow)
    known = set(templates)
    settings = tenant.note_settings
    favourite = user.preferences.note_template if user else None
    # Settings that still name a template the clinic no longer has show without it.
    gone = {settings.default, *settings.enabled, *settings.rules.values()} - known
    return NoteCatalog(
        templates=tuple(templates.values()),
        settings=settings.without(gone),
        favourite=favourite if favourite in known else None,
        can_configure=can_configure_notes(uow, actor, tenant),
        custom_allowed=custom_allowed(uow, tenant),
    )


class GetNoteCatalog:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> NoteCatalog:
        return _catalog(self._uow, actor, _tenant(self._uow, actor))


class UpdateNoteSettings:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, settings: NoteSettings) -> NoteCatalog:
        tenant = _tenant(self._uow, actor)
        if not can_configure_notes(self._uow, actor, tenant):
            raise PermissionDenied(
                "only the clinic admin configures note templates", code="note.cannot_configure"
            )
        known = available_templates(self._uow)
        used = {settings.default, *settings.enabled, *settings.rules.values()}
        if used - set(known):
            raise ValidationError("Unknown note template", code="note.unknown_template")
        before = tenant.note_settings
        with self._uow:
            tenant.note_settings = settings
            self._uow.tenants.save(tenant)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "organization.note_settings_updated", "Tenant",
                    str(tenant.id), subject=subject(tenant.legal_name),
                    before=_settings_dict(before), after=_settings_dict(settings),
                )
            )
            self._uow.commit()
            return _catalog(self._uow, actor, tenant)


def _settings_dict(s: NoteSettings) -> dict:
    return {"enabled": list(s.enabled), "default": s.default, "rules": dict(s.rules),
            "locked": s.locked}


class SetFavouriteNoteTemplate:
    """The doctor's own preferred template; ``None`` clears it."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext, template: str | None) -> NoteCatalog:
        if template is not None:
            find_template(self._uow, template)
        user = self._uow.users.get_by_id(actor.user_id)
        if user is None:
            raise EntityNotFound("User", actor.user_id)
        with self._uow:
            user.set_note_template(template)
            self._uow.users.save(user)
            self._uow.commit()
            return _catalog(self._uow, actor, _tenant(self._uow, actor))


# ── The clinic's own templates ─────────────────────────────────────────────────
class _CustomTemplateEditor:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _tenant_for_editing(self, actor: ActorContext) -> Tenant:
        tenant = _tenant(self._uow, actor)
        if not can_configure_notes(self._uow, actor, tenant):
            raise PermissionDenied(
                "only the clinic admin configures note templates", code="note.cannot_configure"
            )
        if not custom_allowed(self._uow, tenant):
            raise PermissionDenied(
                "the plan does not include custom note templates",
                code="plan.feature_required", feature=str(PlanFeature.CUSTOM_NOTE_TEMPLATES),
            )
        return tenant

    def _load(self, template_id: NoteTemplateId) -> CustomNoteTemplate:
        template = self._uow.note_templates.get_by_id(template_id)
        if template is None or template.archived:
            raise EntityNotFound("NoteTemplate", template_id)
        return template

    def _audit(self, actor: ActorContext, action: str, template: CustomNoteTemplate) -> None:
        self._uow.audit.append(
            audit_entry(
                actor, self._clock.now(), action, "NoteTemplate", template.key,
                subject=subject(template.name),
                sections=[s.title for s in template.sections],
            )
        )


class CreateNoteTemplate(_CustomTemplateEditor):
    def execute(
        self, actor: ActorContext, name: str, sections: list[SectionDraft]
    ) -> NoteCatalog:
        tenant = self._tenant_for_editing(actor)
        template = CustomNoteTemplate.create(
            tenant_id=actor.tenant_id, name=name, sections=sections,
            created_by_id=actor.user_id, now=self._clock.now(),
        )
        with self._uow:
            self._uow.note_templates.save(template)
            self._audit(actor, "note_template.created", template)
            self._uow.commit()
            return _catalog(self._uow, actor, tenant)


class UpdateNoteTemplate(_CustomTemplateEditor):
    """Notes already written keep the version they were written with."""

    def execute(
        self, actor: ActorContext, template_id: NoteTemplateId, name: str,
        sections: list[SectionDraft],
    ) -> NoteCatalog:
        tenant = self._tenant_for_editing(actor)
        template = self._load(template_id)
        with self._uow:
            template.revise(name=name, sections=sections, now=self._clock.now())
            self._uow.note_templates.save(template)
            self._audit(actor, "note_template.updated", template)
            self._uow.commit()
            return _catalog(self._uow, actor, tenant)


class ArchiveNoteTemplate(_CustomTemplateEditor):
    """Take a template out of use; the clinic's settings stop naming it. Signed records
    and consultations in progress keep their copy."""

    def execute(self, actor: ActorContext, template_id: NoteTemplateId) -> NoteCatalog:
        tenant = self._tenant_for_editing(actor)
        template = self._load(template_id)
        with self._uow:
            template.archive(self._clock.now())
            self._uow.note_templates.save(template)
            tenant.note_settings = tenant.note_settings.without({template.key})
            self._uow.tenants.save(tenant)
            self._audit(actor, "note_template.archived", template)
            self._uow.commit()
            return _catalog(self._uow, actor, tenant)
