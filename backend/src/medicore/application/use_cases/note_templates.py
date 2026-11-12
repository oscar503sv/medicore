"""Clinical note templates: the catalog a clinic can use, its settings and each doctor's
favourite.

The clinic admin decides which templates are enabled, the default, a template per
appointment type (and for a patient's first visit) and whether the format is mandatory. In
a single-doctor plan there is no admin to ask, so the doctor decides. Doctors keep a
favourite template, used when the clinic sets no rule for the visit.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import Permission, has_permission
from medicore.application.common.quotas import effective_limits
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.tenant import Tenant
from medicore.domain.enums import NoteRole, Role
from medicore.domain.services.note_templates import SYSTEM_TEMPLATES
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.clinical_note import ClinicalNote, NoteTemplate
from medicore.domain.value_objects.note_settings import NoteSettings


@dataclass(frozen=True, slots=True)
class NoteCatalog:
    templates: tuple[NoteTemplate, ...]  # every template the clinic has
    settings: NoteSettings
    favourite: str | None  # the actor's own
    can_configure: bool

    @property
    def allowed(self) -> tuple[str, ...]:
        return tuple(t.key for t in self.templates if self.settings.allows(t.key))


def available_templates(uow: UnitOfWork) -> dict[str, NoteTemplate]:
    """The templates a clinic can use (built in only, for now)."""
    del uow  # custom clinic templates will come from the unit of work
    return dict(SYSTEM_TEMPLATES)


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
    return NoteCatalog(
        templates=tuple(available_templates(uow).values()),
        settings=tenant.note_settings,
        favourite=user.preferences.note_template if user else None,
        can_configure=can_configure_notes(uow, actor, tenant),
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
