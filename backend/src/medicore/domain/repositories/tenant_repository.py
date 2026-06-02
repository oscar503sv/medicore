"""TenantRepository port."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.tenant import Tenant
from medicore.domain.repositories._support import Page, Paging, TenantFilter
from medicore.domain.shared.identifiers import TenantId
from medicore.domain.value_objects.slug import Slug


class TenantRepository(Protocol):
    """Tenant is the multi-tenant root, so this repo is *not* tenant-scoped."""

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None: ...

    def get_by_slug(self, slug: Slug) -> Tenant | None: ...

    def list(
        self, filter: TenantFilter | None = None, paging: Paging | None = None
    ) -> Page[Tenant]: ...

    def save(self, tenant: Tenant) -> None: ...
