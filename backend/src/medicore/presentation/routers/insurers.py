"""Insurers router. Listing is open to any authenticated role; mutations are admin-only
(enforced in the use cases)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.insurers import (
    ArchiveInsurer,
    CreateInsurer,
    CreateInsurerCommand,
    ListInsurers,
    UpdateInsurer,
)
from medicore.domain.shared.identifiers import InsurerId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.insurers import (
    CreateInsurerRequest,
    InsurerListResponse,
    InsurerResponse,
    UpdateInsurerRequest,
)
from medicore.presentation.serializers import ser_insurer

router = APIRouter(prefix="/insurers", tags=["insurers"])


@router.get("", response_model=InsurerListResponse)
def list_insurers(actor: Actor, uow: UoW, active_only: bool = Query(False)):
    with uow:
        insurers = ListInsurers(uow).execute(actor, active_only=active_only)
    return InsurerListResponse(items=[ser_insurer(i) for i in insurers])


@router.post("", response_model=InsurerResponse, status_code=201)
def create_insurer(body: CreateInsurerRequest, actor: Actor, uow: UoW, clock: Clock):
    cmd = CreateInsurerCommand(
        name=body.name,
        phone=body.phone,
        email=body.email,
        address=body.address,
        contact_person=body.contact_person,
        notes=body.notes,
    )
    return ser_insurer(CreateInsurer(uow, clock).execute(actor, cmd))


@router.patch("/{insurer_id}", response_model=InsurerResponse)
def update_insurer(
    insurer_id: str, body: UpdateInsurerRequest, actor: Actor, uow: UoW, clock: Clock
):
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    insurer = UpdateInsurer(uow, clock).execute(actor, InsurerId.parse(insurer_id), **changes)
    return ser_insurer(insurer)


@router.post("/{insurer_id}/archive", response_model=InsurerResponse)
def archive_insurer(insurer_id: str, actor: Actor, uow: UoW, clock: Clock):
    return ser_insurer(ArchiveInsurer(uow, clock).execute(actor, InsurerId.parse(insurer_id)))
