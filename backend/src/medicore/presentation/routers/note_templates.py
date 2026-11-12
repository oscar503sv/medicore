"""Clinical note templates router: the catalog, the clinic's settings and each doctor's
favourite."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.note_templates import (
    GetNoteCatalog,
    NoteCatalog,
    SetFavouriteNoteTemplate,
    UpdateNoteSettings,
)
from medicore.domain.value_objects.note_settings import NoteSettings
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.note_templates import (
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
