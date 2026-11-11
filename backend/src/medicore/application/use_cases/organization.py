"""Organization (tenant) use cases (admin).

What stays with the platform console: the slug (never changes), the subscription and the
timezone — changing it moves the clinic's "today", agenda and reminders, so it is set once
with Medicore support. Sites are self-service within the plan's limit (``locations.manage``).
"""

from __future__ import annotations

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.common.quotas import ensure_location_for
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.enums import IcdVersion
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import LocationId


class GetOrganization:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> Tenant:
        ensure_permission(actor, Permission.ORGANIZATION_VIEW)
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        return tenant


class UpdateOrganization:
    # The subscription (plan, limits) and the timezone are not the clinic's to change: only
    # the platform console sets them, so they are deliberately absent here.
    _EDITABLE = {"legal_name", "tax_id", "icd_version"}

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, **changes: object) -> Tenant:
        ensure_permission(actor, Permission.ORGANIZATION_MANAGE)
        tenant = self._require()
        timezone = changes.get("timezone")
        if timezone is not None and timezone != tenant.timezone:
            raise PermissionDenied(
                "the clinic's timezone is changed by Medicore support",
                code="organization.timezone_locked",
            )
        with self._uow:
            for key, value in changes.items():
                if key in self._EDITABLE:
                    if key == "icd_version":
                        value = IcdVersion(value)
                    setattr(tenant, key, value)
            self._uow.tenants.save(tenant)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "organization.updated", "Tenant", str(tenant.id),
                    subject=subject(tenant.legal_name),
                )
            )
            self._uow.commit()
        return tenant

    def _require(self) -> Tenant:
        tenant = self._uow.tenants.get_by_id(self._uow.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", self._uow.tenant_id)
        return tenant


def open_location(
    uow: UnitOfWork, tenant: Tenant, name: str, address: str | None, is_primary: bool = False
) -> Location:
    """Add a site to the clinic within its plan's site limit (shared with the console)."""
    ensure_location_for(uow, tenant)
    location = Location(
        id=LocationId.new(),
        tenant_id=tenant.id,
        name=name,
        address=address,
        is_primary=is_primary,
    )
    tenant.add_location(location)
    return location


class AddLocation:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, name: str, address: str | None = None, is_primary: bool = False
    ) -> Tenant:
        ensure_permission(actor, Permission.LOCATIONS_MANAGE)
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        with self._uow:
            location = open_location(self._uow, tenant, name, address, is_primary)
            self._uow.tenants.save(tenant)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "location.added", "Location", str(location.id),
                    subject=subject(location.name),
                )
            )
            self._uow.commit()
        return tenant


class UpdateLocation:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, location_id: LocationId, **changes: object
    ) -> Tenant:
        ensure_permission(actor, Permission.LOCATIONS_MANAGE)
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        location = next((loc for loc in tenant.locations if loc.id == location_id), None)
        if location is None:
            raise EntityNotFound("Location", location_id)
        with self._uow:
            for key in ("name", "address"):
                if key in changes:
                    setattr(location, key, changes[key])
            self._uow.tenants.save(tenant)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "location.updated", "Location", str(location_id),
                    subject=subject(location.name),
                )
            )
            self._uow.commit()
        return tenant
