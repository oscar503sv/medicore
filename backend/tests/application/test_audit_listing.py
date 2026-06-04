"""Tenant audit listing use case (Phase 3)."""

from __future__ import annotations

import pytest

from medicore.application.common.audit import audit_entry
from medicore.application.use_cases.audit import ListTenantAudit
from medicore.domain.repositories._support import AuditFilter, Paging
from medicore.domain.shared.errors import PermissionDenied
from tests.support.builders import seed_clinic


def _seed_trail(seed):
    uow = seed.factory.for_tenant(seed.tenant.id)
    actor = seed.actor(seed.admin)
    with uow:
        for action, entity in [
            ("patient.created", "Patient"),
            ("patient.updated", "Patient"),
            ("record.amended", "MedicalRecord"),
            ("user.invited", "User"),
        ]:
            uow.audit.append(
                audit_entry(actor, seed_clock_now(), action, entity, "e1")
            )
        uow.commit()


def seed_clock_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def test_list_tenant_audit_admin_only():
    seed = seed_clinic()
    with pytest.raises(PermissionDenied):
        ListTenantAudit(seed.factory.for_tenant(seed.tenant.id)).execute(seed.doctor_actor)


def test_list_tenant_audit_filters_by_category():
    seed = seed_clinic()
    _seed_trail(seed)
    page = ListTenantAudit(seed.factory.for_tenant(seed.tenant.id)).execute(
        seed.actor(seed.admin), AuditFilter(category="patient")
    )
    assert page.total == 2
    assert {e.action for e in page.items} == {"patient.created", "patient.updated"}


def test_list_tenant_audit_filters_by_entity_and_paginates():
    seed = seed_clinic()
    _seed_trail(seed)
    page = ListTenantAudit(seed.factory.for_tenant(seed.tenant.id)).execute(
        seed.actor(seed.admin), AuditFilter(entity_type="MedicalRecord"), Paging(offset=0, limit=10)
    )
    assert page.total == 1
    assert page.items[0].action == "record.amended"
