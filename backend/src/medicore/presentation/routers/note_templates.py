"""Clinical note templates router: the catalog, the clinic's settings and each doctor's
favourite."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.note_templates import (
    ArchiveNoteTemplate,
    CreateNoteTemplate,
    GetNoteCatalog,
    NoteCatalog,
    SetFavouriteNoteTemplate,
    UpdateNoteSettings,
    UpdateNoteTemplate,
)
from medicore.domain.entities.note_template import SectionDraft
from medicore.domain.shared.identifiers import NoteTemplateId
from medicore.domain.value_objects.note_settings import NoteSettings
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.note_templates import (
    CustomTemplateRequest,
    FavouriteTemplateRequest,
    NoteCatalogResponse,
    NoteSettingsSchema,
)

router = APIRouter(prefix="/note-templates", tags=["note-templates"])


def ser_catalog(c: NoteCatalog) -> dict:
    s = c.settings
    return {
        "templates": [
            {"key": t.key, "name": t.name, "system": t.system,
             "sections": [{"key": x.key, "role": str(x.role), "title": x.title,
                           "required": x.required} for x in t.sections]}
            for t in c.templates
        ],
        "settings": {"enabled": list(s.enabled), "default": s.default, "rules": dict(s.rules),
                     "locked": s.locked},
        "allowed": list(c.allowed),
        "favourite": c.favourite,
        "can_configure": c.can_configure,
        "custom_allowed": c.custom_allowed,
    }


@router.get("", response_model=NoteCatalogResponse)
def get_catalog(actor: Actor, uow: UoW):
    with uow:
        catalog = GetNoteCatalog(uow).execute(actor)
    return ser_catalog(catalog)


@router.put("/settings", response_model=NoteCatalogResponse)
def update_settings(body: NoteSettingsSchema, actor: Actor, uow: UoW, clock: Clock):
    settings = NoteSettings(
        enabled=tuple(dict.fromkeys(body.enabled)), default=body.default,
        rules={k: v for k, v in body.rules.items() if v}, locked=body.locked,
    )
    return ser_catalog(UpdateNoteSettings(uow, clock).execute(actor, settings))


@router.put("/favourite", response_model=NoteCatalogResponse)
def set_favourite(body: FavouriteTemplateRequest, actor: Actor, uow: UoW):
    return ser_catalog(SetFavouriteNoteTemplate(uow).execute(actor, body.template or None))


def _drafts(body: CustomTemplateRequest) -> list[SectionDraft]:
    return [SectionDraft(title=s.title, role=s.role, required=s.required) for s in body.sections]


@router.post("", response_model=NoteCatalogResponse, status_code=201)
def create_template(body: CustomTemplateRequest, actor: Actor, uow: UoW, clock: Clock):
    return ser_catalog(CreateNoteTemplate(uow, clock).execute(actor, body.name, _drafts(body)))


@router.put("/{template_id}", response_model=NoteCatalogResponse)
def update_template(
    template_id: str, body: CustomTemplateRequest, actor: Actor, uow: UoW, clock: Clock
):
    return ser_catalog(UpdateNoteTemplate(uow, clock).execute(
        actor, NoteTemplateId.parse(template_id), body.name, _drafts(body)))


@router.delete("/{template_id}", response_model=NoteCatalogResponse)
def archive_template(template_id: str, actor: Actor, uow: UoW, clock: Clock):
    return ser_catalog(ArchiveNoteTemplate(uow, clock).execute(
        actor, NoteTemplateId.parse(template_id)))
