"""Organization router (admin only)."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.organization import (
    AddLocation,
    GetOrganization,
    UpdateLocation,
    UpdateOrganization,
)
from medicore.domain.shared.identifiers import LocationId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.organization import (
    AddLocationRequest,
    OrganizationResponse,
    UpdateLocationRequest,
    UpdateOrganizationRequest,
)
from medicore.presentation.serializers import ser_tenant

router = APIRouter(prefix="/organization", tags=["organization"])


@router.get("", response_model=OrganizationResponse)
def get_organization(actor: Actor, uow: UoW):
    with uow:
        tenant = GetOrganization(uow).execute(actor)
    return ser_tenant(tenant)


@router.patch("", response_model=OrganizationResponse)
def update_organization(body: UpdateOrganizationRequest, actor: Actor, uow: UoW, clock: Clock):
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    tenant = UpdateOrganization(uow, clock).execute(actor, **changes)
    return ser_tenant(tenant)


@router.post("/locations", response_model=OrganizationResponse, status_code=201)
def add_location(body: AddLocationRequest, actor: Actor, uow: UoW, clock: Clock):
    tenant = AddLocation(uow, clock).execute(
        actor, name=body.name, address=body.address, is_primary=body.is_primary
    )
    return ser_tenant(tenant)


@router.patch("/locations/{location_id}", response_model=OrganizationResponse)
def update_location(
    location_id: str, body: UpdateLocationRequest, actor: Actor, uow: UoW, clock: Clock
):
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    tenant = UpdateLocation(uow, clock).execute(actor, LocationId.parse(location_id), **changes)
    return ser_tenant(tenant)
