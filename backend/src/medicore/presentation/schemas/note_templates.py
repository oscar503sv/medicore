"""Clinical note template schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from medicore.domain.enums import NoteRole


class NoteSectionResponse(BaseModel):
    key: str
    role: str
    title: str
    required: bool


class NoteTemplateResponse(BaseModel):
    key: str
    name: str
    system: bool
    sections: list[NoteSectionResponse]


class NoteSettingsSchema(BaseModel):
    enabled: list[str] = Field(default_factory=list, max_length=50)
    default: str = Field("soap", min_length=1, max_length=40)
    rules: dict[str, str] = Field(default_factory=dict)
    locked: bool = False


class NoteCatalogResponse(BaseModel):
    templates: list[NoteTemplateResponse]
    settings: NoteSettingsSchema
    allowed: list[str]
    favourite: str | None
    can_configure: bool
    custom_allowed: bool


class FavouriteTemplateRequest(BaseModel):
    template: str | None = Field(None, max_length=40)


class SectionInput(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    role: NoteRole
    required: bool = True


class CustomTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sections: list[SectionInput] = Field(min_length=1, max_length=12)
