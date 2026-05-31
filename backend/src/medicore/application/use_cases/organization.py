"""Organization (tenant) use cases (admin)."""

from __future__ import annotations

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import ensure_can_manage_organization
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.shared.identifiers import LocationId


class GetOrganization:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, actor: ActorContext) -> Tenant:
        ensure_can_manage_organization(actor)
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        return tenant


class UpdateOrganization:
    _EDITABLE = {"legal_name", "tax_id", "timezone", "plan", "seat_limit"}

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, **changes: object) -> Tenant:
        ensure_can_manage_organization(actor)
        tenant = self._require()
        with self._uow:
            for key, value in changes.items():
                if key in self._EDITABLE:
                    setattr(tenant, key, value)
            self._uow.tenants.save(tenant)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "organization.updated", "Tenant", str(tenant.id)
                )
            )
            self._uow.commit()
        return tenant

    def _require(self) -> Tenant:
        tenant = self._uow.tenants.get_by_id(self._uow.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", self._uow.tenant_id)
        return tenant


class AddLocation:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, actor: ActorContext, name: str, address: str | None = None, is_primary: bool = False
    ) -> Tenant:
        ensure_can_manage_organization(actor)
        tenant = self._uow.tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        location = Location(
            id=LocationId.new(),
            tenant_id=tenant.id,
            name=name,
            address=address,
            is_primary=is_primary,
        )
        with self._uow:
            tenant.add_location(location)
            self._uow.tenants.save(tenant)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "location.added", "Location", str(location.id)
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
        ensure_can_manage_organization(actor)
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
                    actor, self._clock.now(), "location.updated", "Location", str(location_id)
                )
            )
            self._uow.commit()
        return tenant
