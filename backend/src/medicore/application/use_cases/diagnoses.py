"""Diagnosis catalog use cases — autocomplete search scoped to the clinic's CIE version."""

from __future__ import annotations

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.common.permissions import Permission, ensure_permission
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.entities.diagnosis_catalog import CatalogDiagnosis


class GetDiagnosisConfig:
    """Return the CIE version configured for the actor's clinic (for the UI header)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext) -> str:
        ensure_permission(actor, Permission.DIAGNOSES_VIEW)
        with self._factory.global_tenants() as tenants:
            tenant = tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        return str(tenant.icd_version)


class SearchDiagnoses:
    """Search the diagnosis catalog using the actor clinic's configured CIE version."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext, query: str, limit: int = 20) -> list[CatalogDiagnosis]:
        ensure_permission(actor, Permission.DIAGNOSES_VIEW)
        with self._factory.global_tenants() as tenants:
            tenant = tenants.get_by_id(actor.tenant_id)
        if tenant is None:
            raise EntityNotFound("Tenant", actor.tenant_id)
        with self._factory.diagnosis_catalog() as catalog:
            return catalog.search(str(tenant.icd_version), query, limit)
