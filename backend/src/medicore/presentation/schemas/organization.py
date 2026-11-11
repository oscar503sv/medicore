"""Organization schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from medicore.domain.enums import PaperSize


class UpdateOrganizationRequest(BaseModel):
    legal_name: str | None = None
    tax_id: str | None = None
    timezone: str | None = None


class AddLocationRequest(BaseModel):
    name: str
    address: str | None = None
    phone: str | None = Field(None, max_length=50)
    is_primary: bool = False


class UpdateLocationRequest(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = Field(None, max_length=50)


class PrintSettingsSchema(BaseModel):
    paper: PaperSize = PaperSize.HALF_LETTER
    letterhead: bool = False


class LocationResponse(BaseModel):
    id: str
    name: str
    address: str | None
    phone: str | None = None
    is_primary: bool


class OrganizationResponse(BaseModel):
    id: str
    legal_name: str
    tax_id: str
    slug: str
    timezone: str
    print_settings: PrintSettingsSchema
    locations: list[LocationResponse]
