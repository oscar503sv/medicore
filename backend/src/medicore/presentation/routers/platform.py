"""Platform (superadmin) router — cross-tenant administration. Login carries no org slug."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.platform import (
    AuthenticatePlatformAdmin,
    CreateTenantCommand,
    CreateTenantWithAdmin,
    GetPlatformAdmin,
    GetTenant,
    ListTenants,
    SetTenantStatus,
    UpdateTenant,
)
from medicore.domain.enums import IcdVersion, TenantStatus
from medicore.domain.repositories._support import Paging, TenantFilter
from medicore.domain.shared.identifiers import TenantId
from medicore.presentation.dependencies import Clock, Hasher, JwtIssuer, PlatformActor, UoWFactory
from medicore.presentation.schemas.platform import (
    CreateTenantRequest,
    CreateTenantResponse,
    PlatformAdminResponse,
    PlatformLoginRequest,
    PlatformSessionResponse,
    SetTenantStatusRequest,
    TenantListResponse,
    TenantResponse,
    UpdateTenantRequest,
)
from medicore.presentation.serializers import ser_platform_admin, ser_tenant

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/login", response_model=PlatformSessionResponse)
def login(body: PlatformLoginRequest, factory: UoWFactory, hasher: Hasher, issuer: JwtIssuer,
          clock: Clock):
    session = AuthenticatePlatformAdmin(factory, hasher, issuer, clock).execute(
        body.email, body.password
    )
    return PlatformSessionResponse(
        token=session.token,
        admin_id=str(session.admin_id),
        name=session.name,
        email=session.email,
    )


@router.get("/me", response_model=PlatformAdminResponse)
def me(actor: PlatformActor, factory: UoWFactory):
    return ser_platform_admin(GetPlatformAdmin(factory).execute(actor))


@router.get("/tenants", response_model=TenantListResponse)
def list_tenants(
    actor: PlatformActor,
    factory: UoWFactory,
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    f = TenantFilter(status=status) if status else None
    page = ListTenants(factory).execute(actor, f, Paging(offset=offset, limit=limit))
    return TenantListResponse(
        items=[ser_tenant(t) for t in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.post("/tenants", response_model=CreateTenantResponse, status_code=201)
def create_tenant(body: CreateTenantRequest, actor: PlatformActor, factory: UoWFactory,
                  hasher: Hasher, clock: Clock):
    cmd = CreateTenantCommand(
        legal_name=body.legal_name,
        tax_id=body.tax_id,
        slug=body.slug,
        timezone=body.timezone,
        icd_version=IcdVersion(body.icd_version),
        location_name=body.location_name,
        admin_name=body.admin_name,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
    )
    result = CreateTenantWithAdmin(factory, hasher, clock).execute(actor, cmd)
    return CreateTenantResponse(
        tenant=ser_tenant(result.tenant),
        admin_user_id=str(result.admin.id),
        admin_email=result.admin.email,
    )


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, actor: PlatformActor, factory: UoWFactory):
    return ser_tenant(GetTenant(factory).execute(actor, TenantId.parse(tenant_id)))


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: str, body: UpdateTenantRequest, actor: PlatformActor,
                  factory: UoWFactory, clock: Clock):
    changes = body.model_dump(exclude_none=True)
    tenant = UpdateTenant(factory, clock).execute(actor, TenantId.parse(tenant_id), **changes)
    return ser_tenant(tenant)


@router.post("/tenants/{tenant_id}/status", response_model=TenantResponse)
def set_tenant_status(tenant_id: str, body: SetTenantStatusRequest, actor: PlatformActor,
                      factory: UoWFactory, clock: Clock):
    tenant = SetTenantStatus(factory, clock).execute(
        actor, TenantId.parse(tenant_id), TenantStatus(body.status)
    )
    return ser_tenant(tenant)
