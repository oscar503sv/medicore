"""SQLAlchemy TenantRepository and LocationRepository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.tenant import Tenant
from medicore.domain.repositories._support import Page, Paging, TenantFilter
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

    def list(
        self, filter: TenantFilter | None = None, paging: Paging | None = None
    ) -> Page[Tenant]:
        q = self._s.query(TenantModel).order_by(TenantModel.legal_name)
        if filter and filter.status:
            q = q.filter(TenantModel.status == filter.status)
        total = q.count()
        pg = paging or Paging()
        rows = q.offset(pg.offset).limit(pg.limit).all()
        return Page(
            items=[to_tenant(r) for r in rows], total=total, offset=pg.offset, limit=pg.limit
        )

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
        row.status = str(tenant.status)
        row.icd_version = str(tenant.icd_version)
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
