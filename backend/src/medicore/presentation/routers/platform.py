"""Platform (superadmin) router — cross-tenant administration. Login carries no org slug."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from medicore.application.common.timezone import tenant_today
from medicore.application.ports.clock import Clock as ClockPort
from medicore.application.use_cases.platform import (
    AddTenantLocation,
    AuthenticatePlatformAdmin,
    CreateTenantCommand,
    CreateTenantWithAdmin,
    EndImpersonation,
    GetGlobalStats,
    GetPlatformAdmin,
    GetTenant,
    GetTenantPermissionsMatrix,
    GetTenantStats,
    ImpersonateTenant,
    ListGlobalAudit,
    ListTenants,
    ListTenantUsers,
    ResetTenantRolePermissions,
    ResetUserPassword,
    SetTenantStatus,
    SuspendTenantUser,
    UnlockUser,
    UpdateTenant,
    UpdateTenantRolePermissions,
    UpdateTenantUser,
)
from medicore.application.use_cases.sessions import ListTenantSessions, RevokeTenantSession
from medicore.application.use_cases.subscriptions import SubscriptionCommand
from medicore.domain.entities.tenant import Tenant
from medicore.domain.repositories._support import Paging, TenantFilter
from medicore.domain.shared.identifiers import SessionId, TenantId, UserId
from medicore.domain.value_objects.subscription import DEFAULT_GRACE_DAYS
from medicore.infrastructure.config import get_settings
from medicore.presentation.cookies import (
    PLATFORM_COOKIE,
    SESSION_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from medicore.presentation.dependencies import (
    Actor,
    Clock,
    Hasher,
    JwtIssuer,
    PlatformActor,
    UoWFactory,
    revoke_session_token,
)
from medicore.presentation.routers.role_permissions import parse_role, ser_matrix
from medicore.presentation.schemas.auth import SessionListResponse
from medicore.presentation.schemas.platform import (
    AddTenantLocationRequest,
    CreateTenantRequest,
    CreateTenantResponse,
    GlobalAuditListResponse,
    GlobalStatsResponse,
    ImpersonateRequest,
    ImpersonationResponse,
    PlatformAdminResponse,
    PlatformLoginRequest,
    PlatformSessionResponse,
    ResetPasswordRequest,
    SetTenantStatusRequest,
    TenantListResponse,
    TenantResponse,
    TenantStatsResponse,
    UpdateTenantRequest,
    UpdateTenantUserRequest,
)
from medicore.presentation.schemas.role_permissions import (
    PermissionsMatrixResponse,
    UpdateRolePermissionsRequest,
)
from medicore.presentation.schemas.users import UserListResponse
from medicore.presentation.serializers import (
    ser_global_audit_row,
    ser_global_stats,
    ser_platform_admin,
    ser_session_info,
    ser_tenant,
    ser_tenant_stats,
    ser_user,
)

router = APIRouter(prefix="/platform", tags=["platform"])


def _ser(tenant: Tenant, clock: ClockPort) -> dict:
    """A clinic as the console shows it, subscription status as of the clinic's today."""
    return ser_tenant(tenant, today=tenant_today(tenant, clock))


@router.post("/login", response_model=PlatformSessionResponse)
def login(body: PlatformLoginRequest, response: Response, factory: UoWFactory, hasher: Hasher,
          issuer: JwtIssuer, clock: Clock):
    session = AuthenticatePlatformAdmin(factory, hasher, issuer, clock).execute(
        body.email, body.password
    )
    set_session_cookies(
        response,
        cookie_name=PLATFORM_COOKIE,
        token=session.token,
        max_age=get_settings().jwt_expire_minutes * 60,
    )
    return PlatformSessionResponse(
        admin_id=str(session.admin_id),
        name=session.name,
        email=session.email,
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    factory: UoWFactory,
    issuer: JwtIssuer,
    clock: Clock,
):
    """Revoke the server-side session (best effort) and clear the platform cookies."""
    revoke_session_token(request.cookies.get(PLATFORM_COOKIE), issuer, factory, clock.now())
    clear_session_cookies(response, PLATFORM_COOKIE)


@router.get("/me", response_model=PlatformAdminResponse)
def me(actor: PlatformActor, factory: UoWFactory):
    return ser_platform_admin(GetPlatformAdmin(factory).execute(actor))


@router.get("/tenants", response_model=TenantListResponse)
def list_tenants(
    actor: PlatformActor,
    factory: UoWFactory,
    clock: Clock,
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    f = TenantFilter(status=status) if status else None
    page = ListTenants(factory).execute(actor, f, Paging(offset=offset, limit=limit))
    return TenantListResponse(
        items=[_ser(t, clock) for t in page.items],
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
        icd_version=body.icd_version,
        location_name=body.location_name,
        admin_name=body.admin_name,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
        subscription=SubscriptionCommand(
            plan_code=body.plan_code,
            modules=frozenset(body.modules),
            period_end=body.period_end,
            is_trial=False,
            grace_days=DEFAULT_GRACE_DAYS,
        ),
        trial_days=body.trial_days,
    )
    result = CreateTenantWithAdmin(factory, hasher, clock).execute(actor, cmd)
    return CreateTenantResponse(
        tenant=_ser(result.tenant, clock),
        admin_user_id=str(result.admin.id),
        admin_email=result.admin.email,
    )


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, actor: PlatformActor, factory: UoWFactory, clock: Clock):
    return _ser(GetTenant(factory).execute(actor, TenantId.parse(tenant_id)), clock)


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: str, body: UpdateTenantRequest, actor: PlatformActor,
                  factory: UoWFactory, clock: Clock):
    changes = body.model_dump(exclude_none=True)
    tenant = UpdateTenant(factory, clock).execute(actor, TenantId.parse(tenant_id), **changes)
    return _ser(tenant, clock)


@router.post("/tenants/{tenant_id}/locations", response_model=TenantResponse, status_code=201)
def add_tenant_location(tenant_id: str, body: AddTenantLocationRequest, actor: PlatformActor,
                        factory: UoWFactory, clock: Clock):
    tenant = AddTenantLocation(factory, clock).execute(
        actor, TenantId.parse(tenant_id), name=body.name, address=body.address
    )
    return _ser(tenant, clock)


@router.post("/tenants/{tenant_id}/status", response_model=TenantResponse)
def set_tenant_status(tenant_id: str, body: SetTenantStatusRequest, actor: PlatformActor,
                      factory: UoWFactory, clock: Clock):
    tenant = SetTenantStatus(factory, clock).execute(
        actor, TenantId.parse(tenant_id), body.status
    )
    return _ser(tenant, clock)


# ── Statistics & audit ─────────────────────────────────────────────────────────


@router.get("/stats", response_model=GlobalStatsResponse)
def global_stats(actor: PlatformActor, factory: UoWFactory):
    return ser_global_stats(GetGlobalStats(factory).execute(actor))


@router.get("/tenants/{tenant_id}/stats", response_model=TenantStatsResponse)
def tenant_stats(tenant_id: str, actor: PlatformActor, factory: UoWFactory):
    return ser_tenant_stats(GetTenantStats(factory).execute(actor, TenantId.parse(tenant_id)))


@router.get("/audit", response_model=GlobalAuditListResponse)
def global_audit(
    actor: PlatformActor,
    factory: UoWFactory,
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    page = ListGlobalAudit(factory).execute(
        actor, limit=limit, offset=offset, category=category
    )
    return GlobalAuditListResponse(
        items=[ser_global_audit_row(r) for r in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


# ── Account support (cross-tenant) ─────────────────────────────────────────────


@router.get("/tenants/{tenant_id}/users", response_model=UserListResponse)
def list_tenant_users(
    tenant_id: str,
    actor: PlatformActor,
    factory: UoWFactory,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    page = ListTenantUsers(factory).execute(
        actor, TenantId.parse(tenant_id), Paging(offset=offset, limit=limit)
    )
    return UserListResponse(
        items=[ser_user(u) for u in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/tenants/{tenant_id}/sessions", response_model=SessionListResponse)
def list_tenant_sessions(tenant_id: str, actor: PlatformActor, factory: UoWFactory, clock: Clock):
    sessions = ListTenantSessions(factory, clock).execute(actor, TenantId.parse(tenant_id))
    return SessionListResponse(items=[ser_session_info(s) for s in sessions])


@router.delete("/tenants/{tenant_id}/sessions/{session_id}", status_code=204)
def revoke_tenant_session(
    tenant_id: str, session_id: str, actor: PlatformActor, factory: UoWFactory, clock: Clock
):
    RevokeTenantSession(factory, clock).execute(
        actor, TenantId.parse(tenant_id), SessionId.parse(session_id)
    )


@router.post("/tenants/{tenant_id}/users/{user_id}/reset-password", response_model=UserListResponse)
def reset_user_password(tenant_id: str, user_id: str, body: ResetPasswordRequest,
                        actor: PlatformActor, factory: UoWFactory, hasher: Hasher, clock: Clock):
    ResetUserPassword(factory, hasher, clock).execute(
        actor, TenantId.parse(tenant_id), UserId.parse(user_id), body.password
    )
    page = ListTenantUsers(factory).execute(actor, TenantId.parse(tenant_id))
    return UserListResponse(
        items=[ser_user(u) for u in page.items], total=page.total, offset=page.offset,
        limit=page.limit,
    )


@router.post("/tenants/{tenant_id}/users/{user_id}/unlock", response_model=UserListResponse)
def unlock_user(tenant_id: str, user_id: str, actor: PlatformActor, factory: UoWFactory,
                clock: Clock):
    UnlockUser(factory, clock).execute(
        actor, TenantId.parse(tenant_id), UserId.parse(user_id)
    )
    page = ListTenantUsers(factory).execute(actor, TenantId.parse(tenant_id))
    return UserListResponse(
        items=[ser_user(u) for u in page.items], total=page.total, offset=page.offset,
        limit=page.limit,
    )


@router.patch("/tenants/{tenant_id}/users/{user_id}", response_model=UserListResponse)
def update_tenant_user(tenant_id: str, user_id: str, body: UpdateTenantUserRequest,
                       actor: PlatformActor, factory: UoWFactory, clock: Clock):
    changes = body.model_dump(exclude_none=True)
    UpdateTenantUser(factory, clock).execute(
        actor, TenantId.parse(tenant_id), UserId.parse(user_id), **changes
    )
    page = ListTenantUsers(factory).execute(actor, TenantId.parse(tenant_id))
    return UserListResponse(
        items=[ser_user(u) for u in page.items], total=page.total, offset=page.offset,
        limit=page.limit,
    )


@router.post("/tenants/{tenant_id}/users/{user_id}/suspend", response_model=UserListResponse)
def suspend_tenant_user(tenant_id: str, user_id: str, actor: PlatformActor, factory: UoWFactory,
                        clock: Clock):
    SuspendTenantUser(factory, clock).execute(
        actor, TenantId.parse(tenant_id), UserId.parse(user_id)
    )
    page = ListTenantUsers(factory).execute(actor, TenantId.parse(tenant_id))
    return UserListResponse(
        items=[ser_user(u) for u in page.items], total=page.total, offset=page.offset,
        limit=page.limit,
    )


@router.post("/tenants/{tenant_id}/impersonate", response_model=ImpersonationResponse)
def impersonate(tenant_id: str, body: ImpersonateRequest, response: Response,
                actor: PlatformActor, factory: UoWFactory, issuer: JwtIssuer, clock: Clock):
    s = ImpersonateTenant(factory, issuer, clock).execute(
        actor, TenantId.parse(tenant_id), body.reason
    )
    # The support session is a TENANT session: set the tenant cookie so the superadmin
    # can use the clinic app, with the shorter support TTL.
    set_session_cookies(
        response,
        cookie_name=SESSION_COOKIE,
        token=s.token,
        max_age=get_settings().jwt_support_expire_minutes * 60,
    )
    return ImpersonationResponse(
        user_id=s.user_id,
        tenant_id=s.tenant_id,
        tenant_name=s.tenant_name,
        timezone=s.timezone,
        role=s.role,
        name=s.name,
        permissions=list(s.permissions),
    )


@router.post("/impersonation/end", status_code=204)
def end_impersonation(response: Response, actor: Actor, factory: UoWFactory, clock: Clock):
    """Close the current support session (tenant-scoped: uses the impersonation token)."""
    EndImpersonation(factory, clock).execute(actor)
    clear_session_cookies(response, SESSION_COOKIE)


@router.get("/tenants/{tenant_id}/permissions", response_model=PermissionsMatrixResponse)
def get_tenant_permissions(tenant_id: str, actor: PlatformActor, factory: UoWFactory):
    matrix = GetTenantPermissionsMatrix(factory).execute(actor, TenantId.parse(tenant_id))
    return ser_matrix(matrix)


@router.put(
    "/tenants/{tenant_id}/permissions/roles/{role}", response_model=PermissionsMatrixResponse
)
def update_tenant_role_permissions(
    tenant_id: str,
    role: str,
    body: UpdateRolePermissionsRequest,
    actor: PlatformActor,
    factory: UoWFactory,
    clock: Clock,
):
    matrix = UpdateTenantRolePermissions(factory, clock).execute(
        actor, TenantId.parse(tenant_id), parse_role(role), body.permissions
    )
    return ser_matrix(matrix)


@router.delete(
    "/tenants/{tenant_id}/permissions/roles/{role}", response_model=PermissionsMatrixResponse
)
def reset_tenant_role_permissions(
    tenant_id: str, role: str, actor: PlatformActor, factory: UoWFactory, clock: Clock
):
    matrix = ResetTenantRolePermissions(factory, clock).execute(
        actor, TenantId.parse(tenant_id), parse_role(role)
    )
    return ser_matrix(matrix)
