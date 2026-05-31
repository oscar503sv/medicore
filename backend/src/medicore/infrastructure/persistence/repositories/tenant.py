"""SQLAlchemy TenantRepository and LocationRepository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.tenant import Tenant
from medicore.domain.shared.identifiers import TenantId
from medicore.domain.value_objects.slug import Slug
from medicore.infrastructure.persistence.mappers.entities import to_tenant
from medicore.infrastructure.persistence.models.tenant import LocationModel, TenantModel


class SqlTenantRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        row = self._s.get(TenantModel, tenant_id.value)
        return to_tenant(row) if row else None

    def get_by_slug(self, slug: Slug) -> Tenant | None:
        row = (
            self._s.query(TenantModel).filter(TenantModel.slug == str(slug)).first()
        )
        return to_tenant(row) if row else None

    def save(self, tenant: Tenant) -> None:
        row = self._s.get(TenantModel, tenant.id.value)
        if row is None:
            row = TenantModel(id=tenant.id.value)
            self._s.add(row)
        row.legal_name = tenant.legal_name
        row.tax_id = tenant.tax_id
        row.slug = str(tenant.slug)
        row.timezone = tenant.timezone
        row.plan = tenant.plan
        row.seat_limit = tenant.seat_limit
        row.created_at = tenant.created_at

        # Sync locations
        domain_ids = {loc.id.value for loc in tenant.locations}
        # Remove deleted
        for loc_row in list(row.locations or []):
            if loc_row.id not in domain_ids:
                self._s.delete(loc_row)
        # Upsert
        for loc in tenant.locations:
            matching = [r for r in (row.locations or []) if r.id == loc.id.value]
            loc_row = matching[0] if matching else None
            if loc_row is None:
                loc_row = LocationModel(id=loc.id.value, tenant_id=tenant.id.value)
                row.locations.append(loc_row)
            loc_row.name = loc.name
            loc_row.address = loc.address
            loc_row.is_primary = loc.is_primary
