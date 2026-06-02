"""Platform (superadmin) use cases — cross-tenant administration.

These operate above the multi-tenant boundary via the ``UnitOfWorkFactory``: ``platform_uow()``
for global reads/writes (tenants, platform admins, platform audit) and ``for_tenant()`` when a
specific clinic's data must be touched atomically (e.g. seeding its first admin user).
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import (
    AuthenticationFailed,
    EntityNotFound,
    ValidationError,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.password_hasher import PasswordHasher
from medicore.application.ports.token_issuer import SessionClaims, TokenIssuer
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import IcdVersion, Role, TenantStatus, UserStatus
from medicore.domain.repositories._support import Page, Paging, TenantFilter
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import (
    AuditLogId,
    LocationId,
    PlatformAdminId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.slug import Slug


def _audit(
    actor: PlatformActorContext,
    when,
    action: str,
    entity_type: str,
    entity_id: str,
    **metadata: object,
) -> PlatformAuditLog:
    return PlatformAuditLog(
        id=AuditLogId.new(),
        actor_id=actor.admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=dict(metadata),
        timestamp=when,
    )


# ── Auth ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PlatformSessionDTO:
    token: str
    admin_id: PlatformAdminId
    name: str
    email: str


class AuthenticatePlatformAdmin:
    """Authenticate a superadmin by email + password (no organization slug)."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        tokens: TokenIssuer,
        clock: Clock,
    ) -> None:
        self._factory = uow_factory
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock

    def execute(self, email: str, password: str) -> PlatformSessionDTO:
        uow = self._factory.platform_uow()
        admin = uow.platform_admins.get_by_email(email)
        if admin is None or not self._hasher.verify(password, admin.password_hash):
            raise AuthenticationFailed("invalid credentials")
        if not admin.is_active:
            raise AuthenticationFailed("account is not active")
        with uow:
            admin.last_seen_at = self._clock.now()
            uow.platform_admins.save(admin)
            uow.commit()
        token = self._tokens.issue(SessionClaims(user_id=str(admin.id), scope="platform"))
        return PlatformSessionDTO(
            token=token, admin_id=admin.id, name=admin.name, email=admin.email
        )


class GetPlatformAdmin:
    """Return the authenticated superadmin's own profile."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: PlatformActorContext):
        uow = self._factory.platform_uow()
        admin = uow.platform_admins.get_by_id(actor.admin_id)
        if admin is None:
            raise EntityNotFound("PlatformAdmin", actor.admin_id)
        return admin


# ── Tenant management ─────────────────────────────────────────────────────────


class ListTenants:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(
        self,
        actor: PlatformActorContext,
        filter: TenantFilter | None = None,
        paging: Paging | None = None,
    ) -> Page[Tenant]:
        return self._factory.platform_uow().tenants.list(filter, paging)


class GetTenant:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: PlatformActorContext, tenant_id: TenantId) -> Tenant:
        tenant = self._factory.platform_uow().tenants.get_by_id(tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", tenant_id)
        return tenant


@dataclass(frozen=True, slots=True)
class CreateTenantCommand:
    legal_name: str
    tax_id: str
    slug: str
    timezone: str
    location_name: str
    admin_name: str
    admin_email: str
    admin_password: str
    icd_version: IcdVersion = IcdVersion.CIE11


@dataclass(frozen=True, slots=True)
class CreateTenantResult:
    tenant: Tenant
    admin: User


class CreateTenantWithAdmin:
    """Onboarding wizard: create a clinic, its primary location and its first admin user.

    The admin gets a temporary password and must change it on first login. Tenant + user +
    audit are committed atomically in the new tenant's unit of work.
    """

    def __init__(
        self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock
    ) -> None:
        self._factory = uow_factory
        self._hasher = hasher
        self._clock = clock

    def execute(self, actor: PlatformActorContext, cmd: CreateTenantCommand) -> CreateTenantResult:
        try:
            slug = Slug(cmd.slug.strip().lower())
        except InvalidValueObject as exc:
            raise ValidationError(str(exc)) from exc
        if not cmd.admin_password or len(cmd.admin_password) < 8:
            raise ValidationError("temporary password must be at least 8 characters")

        platform = self._factory.platform_uow()
        if platform.tenants.get_by_slug(slug) is not None:
            raise ValidationError(f"slug already in use: {slug}")

        tenant_id = TenantId.new()
        tenant = Tenant(
            id=tenant_id,
            legal_name=cmd.legal_name,
            tax_id=cmd.tax_id,
            slug=slug,
            timezone=cmd.timezone,
            icd_version=cmd.icd_version,
            locations=[
                Location(
                    id=LocationId.new(),
                    tenant_id=tenant_id,
                    name=cmd.location_name,
                    is_primary=True,
                )
            ],
        )
        admin = User(
            id=UserId.new(),
            tenant_id=tenant_id,
            name=cmd.admin_name,
            email=cmd.admin_email.strip().lower(),
            password_hash=self._hasher.hash(cmd.admin_password),
            role=Role.ADMIN,
            status=UserStatus.ACTIVE,
            must_change_password=True,
            joined_at=self._clock.now(),
        )
        uow = self._factory.for_tenant(tenant_id)
        with uow:
            uow.tenants.save(tenant)
            uow.users.save(admin)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), "tenant.created", "Tenant", str(tenant_id),
                    slug=str(slug), admin_email=admin.email,
                )
            )
            uow.commit()
        return CreateTenantResult(tenant=tenant, admin=admin)


_EDITABLE = {"legal_name", "tax_id", "timezone", "plan", "seat_limit", "icd_version"}


class UpdateTenant:
    """Edit a clinic's profile fields. Slug and status are changed elsewhere."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, **changes: object
    ) -> Tenant:
        uow = self._factory.for_tenant(tenant_id)
        tenant = uow.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", tenant_id)
        with uow:
            for key, value in changes.items():
                if key in _EDITABLE and value is not None:
                    if key == "icd_version":
                        value = IcdVersion(value)
                    setattr(tenant, key, value)
            uow.tenants.save(tenant)
            uow.platform_audit.append(
                _audit(actor, self._clock.now(), "tenant.updated", "Tenant", str(tenant_id))
            )
            uow.commit()
        return tenant


class SetTenantStatus:
    """Suspend, activate or archive a clinic. Suspended/archived clinics cannot log in."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, status: TenantStatus
    ) -> Tenant:
        uow = self._factory.for_tenant(tenant_id)
        tenant = uow.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", tenant_id)
        with uow:
            tenant.status = status
            uow.tenants.save(tenant)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), f"tenant.{status}", "Tenant", str(tenant_id),
                    status=str(status),
                )
            )
            uow.commit()
        return tenant
