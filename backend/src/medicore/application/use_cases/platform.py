"""Platform (superadmin) use cases — cross-tenant administration.

These operate above the multi-tenant boundary via the ``UnitOfWorkFactory``: ``platform_uow()``
for global reads/writes (tenants, platform admins, platform audit) and ``for_tenant()`` when a
specific clinic's data must be touched atomically (e.g. seeding its first admin user).
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.context import ActorContext, PlatformActorContext
from medicore.application.common.errors import (
    AuthenticationFailed,
    EntityNotFound,
    ValidationError,
)
from medicore.application.ports.clock import Clock
from medicore.application.ports.password_hasher import PasswordHasher
from medicore.application.ports.token_issuer import SessionClaims, TokenIssuer
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import IcdVersion, Role, TenantStatus, UserStatus
from medicore.domain.repositories._support import Page, Paging, TenantFilter, UserFilter
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
    *,
    tenant_id: TenantId | None = None,
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
        tenant_id=tenant_id,
        ip_address=actor.ip_address,
        user_agent=actor.user_agent,
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
        with self._factory.platform_uow() as uow:
            admin = uow.platform_admins.get_by_email(email)
            if admin is None or not self._hasher.verify(password, admin.password_hash):
                raise AuthenticationFailed("invalid credentials")
            if not admin.is_active:
                raise AuthenticationFailed("account is not active")
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
        with self._factory.platform_uow() as uow:
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
        with self._factory.platform_uow() as uow:
            return uow.tenants.list(filter, paging)


class GetTenant:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: PlatformActorContext, tenant_id: TenantId) -> Tenant:
        with self._factory.platform_uow() as uow:
            tenant = uow.tenants.get_by_id(tenant_id)
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

        with self._factory.platform_uow() as platform:
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
                    tenant_id=tenant_id, slug=str(slug), admin_email=admin.email,
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
        location_name = changes.pop("location_name", None)
        with self._factory.for_tenant(tenant_id) as uow:
            tenant = uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                raise EntityNotFound("Tenant", tenant_id)
            for key, value in changes.items():
                if key in _EDITABLE and value is not None:
                    if key == "icd_version":
                        value = IcdVersion(value)
                    setattr(tenant, key, value)
            if location_name:
                # The clinic's primary site (sede) can be renamed after creation.
                tenant.primary_location.name = str(location_name)
            uow.tenants.save(tenant)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), "tenant.updated", "Tenant", str(tenant_id),
                    tenant_id=tenant_id,
                )
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
        with self._factory.for_tenant(tenant_id) as uow:
            tenant = uow.tenants.get_by_id(tenant_id)
            if tenant is None:
                raise EntityNotFound("Tenant", tenant_id)
            tenant.status = status
            uow.tenants.save(tenant)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), f"tenant.{status}", "Tenant", str(tenant_id),
                    tenant_id=tenant_id, status=str(status),
                )
            )
            uow.commit()
        return tenant


# ── Statistics ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TenantStatsDTO:
    tenant_id: str
    legal_name: str
    status: str
    patients: int
    users: int
    appointments: int
    consultations: int
    records: int


@dataclass(frozen=True, slots=True)
class GlobalStatsDTO:
    total_clinics: int
    active_clinics: int
    total_patients: int
    total_users: int
    total_appointments: int
    by_clinic: list[TenantStatsDTO]


def _counts_to_stats(tenant: Tenant, counts: dict[str, int]) -> TenantStatsDTO:
    return TenantStatsDTO(
        tenant_id=str(tenant.id),
        legal_name=tenant.legal_name,
        status=str(tenant.status),
        patients=counts.get("patients", 0),
        users=counts.get("users", 0),
        appointments=counts.get("appointments", 0),
        consultations=counts.get("consultations", 0),
        records=counts.get("records", 0),
    )


class GetGlobalStats:
    """Aggregate counts across every clinic plus per-clinic breakdown."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: PlatformActorContext) -> GlobalStatsDTO:
        with self._factory.platform_uow() as uow:
            tenants = uow.tenants.list(paging=Paging(limit=1000)).items
        with self._factory.platform_reads() as reads:
            counts = reads.counts_by_tenant()
        by_clinic = [_counts_to_stats(t, counts.get(str(t.id), {})) for t in tenants]
        return GlobalStatsDTO(
            total_clinics=len(tenants),
            active_clinics=sum(1 for t in tenants if t.is_active),
            total_patients=sum(c.patients for c in by_clinic),
            total_users=sum(c.users for c in by_clinic),
            total_appointments=sum(c.appointments for c in by_clinic),
            by_clinic=by_clinic,
        )


class GetTenantStats:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: PlatformActorContext, tenant_id: TenantId) -> TenantStatsDTO:
        with self._factory.platform_uow() as uow:
            tenant = uow.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", tenant_id)
        with self._factory.platform_reads() as reads:
            counts = reads.tenant_counts(tenant_id)
        return _counts_to_stats(tenant, counts)


class ListGlobalAudit:
    """Read the per-tenant audit trail across all clinics (most recent first)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(
        self,
        actor: PlatformActorContext,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        category: str | None = None,
        tenant_id: str | None = None,
    ) -> Page[AuditLog]:
        with self._factory.platform_reads() as reads:
            return reads.global_audit(
                limit=limit, offset=offset, action=action, category=category,
                tenant_id=tenant_id,
            )


# ── Account support (cross-tenant) ─────────────────────────────────────────────


class ListTenantUsers:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, paging: Paging | None = None
    ) -> Page[User]:
        uow = self._factory.for_tenant(tenant_id)
        with uow:
            return uow.users.list(paging=paging)


def _require_user(uow, tenant_id: TenantId, user_id: UserId) -> User:
    user = uow.users.get_by_id(user_id)
    if user is None or user.tenant_id != tenant_id:
        raise EntityNotFound("User", user_id)
    return user


class ResetUserPassword:
    """Superadmin sets a temporary password for a user; they must change it on next login."""

    def __init__(
        self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock
    ) -> None:
        self._factory = uow_factory
        self._hasher = hasher
        self._clock = clock

    def execute(
        self,
        actor: PlatformActorContext,
        tenant_id: TenantId,
        user_id: UserId,
        password: str,
    ) -> User:
        if not password or len(password) < 8:
            raise ValidationError("temporary password must be at least 8 characters")
        with self._factory.for_tenant(tenant_id) as uow:
            user = _require_user(uow, tenant_id, user_id)
            user.set_temporary_password(self._hasher.hash(password))
            uow.users.save(user)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), "user.password_reset", "User", str(user_id),
                    tenant_id=tenant_id,
                )
            )
            uow.commit()
        return user


@dataclass(frozen=True, slots=True)
class ImpersonationSessionDTO:
    token: str
    user_id: str
    tenant_id: str
    tenant_name: str
    timezone: str
    role: str
    name: str


class ImpersonateTenant:
    """Issue a tenant session for support access, tagged with the impersonating superadmin.

    The token authenticates as an active admin of the clinic, but carries an ``impersonator``
    claim so every write made during the session is audited with ``impersonated_by``.
    """

    def __init__(
        self, uow_factory: UnitOfWorkFactory, tokens: TokenIssuer, clock: Clock
    ) -> None:
        self._factory = uow_factory
        self._tokens = tokens
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, reason: str = ""
    ) -> ImpersonationSessionDTO:
        with self._factory.platform_uow() as platform:
            tenant = platform.tenants.get_by_id(tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", tenant_id)
        if tenant.status == TenantStatus.ARCHIVED:
            raise ValidationError("cannot impersonate an archived clinic")
        with self._factory.for_tenant(tenant_id) as uow:
            admins = uow.users.list(filter=UserFilter(role="admin", status="active")).items
            if not admins:
                raise ValidationError("clinic has no active admin to impersonate")
            target = admins[0]
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), "support.access.started", "Tenant", str(tenant_id),
                    tenant_id=tenant_id, as_user=str(target.id), reason=reason.strip(),
                )
            )
            uow.commit()
        token = self._tokens.issue(
            SessionClaims(
                user_id=str(target.id),
                tenant_id=str(tenant_id),
                role=str(target.role),
                scope="tenant",
                impersonator=str(actor.admin_id),
            )
        )
        return ImpersonationSessionDTO(
            token=token,
            user_id=str(target.id),
            tenant_id=str(tenant_id),
            tenant_name=tenant.legal_name,
            timezone=tenant.timezone,
            role=str(target.role),
            name=target.name,
        )


class EndImpersonation:
    """Close a support session, recording who left and which clinic they were in.

    Called with the tenant ``ActorContext`` of the impersonation session itself (its token
    carries ``impersonated_by``), so the ``support.access.ended`` event is attributed to the
    superadmin rather than the impersonated clinic admin.
    """

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(self, actor: ActorContext) -> None:
        if actor.impersonated_by is None:
            raise ValidationError("not a support session")
        with self._factory.for_tenant(actor.tenant_id) as uow:
            uow.platform_audit.append(
                PlatformAuditLog(
                    id=AuditLogId.new(),
                    actor_id=actor.impersonated_by,
                    action="support.access.ended",
                    entity_type="Tenant",
                    entity_id=str(actor.tenant_id),
                    timestamp=self._clock.now(),
                    tenant_id=actor.tenant_id,
                    ip_address=actor.ip_address,
                    user_agent=actor.user_agent,
                )
            )
            uow.commit()


class UnlockUser:
    """Reactivate a suspended user account."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, user_id: UserId
    ) -> User:
        with self._factory.for_tenant(tenant_id) as uow:
            user = _require_user(uow, tenant_id, user_id)
            user.activate()
            uow.users.save(user)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), "user.unlocked", "User", str(user_id),
                    tenant_id=tenant_id,
                )
            )
            uow.commit()
        return user


class UpdateTenantUser:
    """Superadmin edits a tenant user's profile fields (and role). Email is immutable."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self,
        actor: PlatformActorContext,
        tenant_id: TenantId,
        user_id: UserId,
        **changes: object,
    ) -> User:
        allowed = {"name", "role", "sex", "phone", "specialty"}
        with self._factory.for_tenant(tenant_id) as uow:
            user = _require_user(uow, tenant_id, user_id)
            for key, value in changes.items():
                if key in allowed:
                    setattr(user, key, value)
            uow.users.save(user)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), "user.updated", "User", str(user_id),
                    tenant_id=tenant_id,
                )
            )
            uow.commit()
        return user


class SuspendTenantUser:
    """Deactivate a tenant user account."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: PlatformActorContext, tenant_id: TenantId, user_id: UserId
    ) -> User:
        with self._factory.for_tenant(tenant_id) as uow:
            user = _require_user(uow, tenant_id, user_id)
            user.suspend()
            uow.users.save(user)
            uow.platform_audit.append(
                _audit(
                    actor, self._clock.now(), "user.suspended", "User", str(user_id),
                    tenant_id=tenant_id,
                )
            )
            uow.commit()
        return user
