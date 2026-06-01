"""Organization schemas."""

from __future__ import annotations

from pydantic import BaseModel


class UpdateOrganizationRequest(BaseModel):
    legal_name: str | None = None
    tax_id: str | None = None
    timezone: str | None = None
    plan: str | None = None
    seat_limit: int | None = None


class AddLocationRequest(BaseModel):
    name: str
    address: str | None = None
    is_primary: bool = False


class UpdateLocationRequest(BaseModel):
    name: str | None = None
    address: str | None = None


class LocationResponse(BaseModel):
    id: str
    name: str
    address: str | None
    is_primary: bool


class OrganizationResponse(BaseModel):
    id: str
    legal_name: str
    tax_id: str
    slug: str
    timezone: str
    plan: str
    seat_limit: int
    locations: list[LocationResponse]
