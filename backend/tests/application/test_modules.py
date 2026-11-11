"""Optional modules gate their permissions: a clinic that hasn't contracted vaccination,
applications or procedures gets none of their permissions, whatever its roles say."""

from __future__ import annotations

import dataclasses

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.entitlements import granted_permissions
from medicore.application.common.permissions import (
    Permission,
    granted,
    locked_permissions,
)
from medicore.application.use_cases.consultations import (
    AddApplicationDraft,
    AddProcedureDraft,
    StartConsultation,
)
from medicore.application.use_cases.onboarding import GetOnboarding
from medicore.application.use_cases.platform import ImpersonateTenant
from medicore.application.use_cases.role_permissions import GetPermissionsMatrix
from medicore.domain.entities.application import ApplicationDraft
from medicore.domain.enums import AddonModule, ApplicationRoute, Role
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import ProcedureTypeId
from medicore.domain.value_objects.subscription import Subscription
from tests.application.test_consultations import booked
from tests.support.builders import seed_clinic
from tests.support.fakes import FakeTokenIssuer, FixedClock

VACCINATION_ONLY = frozenset({AddonModule.VACCINATION})


def with_modules(seed, modules: frozenset[AddonModule]):
    uow = seed.factory.for_tenant(seed.tenant.id)
    tenant = uow.tenants.get_by_id(seed.tenant.id)
    tenant.subscription = Subscription(plan_code="clinica", modules=modules)
    uow.tenants.save(tenant)
    return uow, tenant


class TestRule:
    def test_uncontracted_modules_lock_their_permissions(self):
        locked = locked_permissions(VACCINATION_ONLY)
        assert Permission.VACCINATIONS_VIEW not in locked
        assert {Permission.APPLICATIONS_VIEW, Permission.PROCEDURES_CATALOG} <= locked

    def test_all_modules_lock_nothing(self):
        assert locked_permissions(frozenset(AddonModule)) == frozenset()

    def test_granted_keeps_the_rest_of_the_role(self):
        perms = granted(Role.DOCTOR, None, frozenset())
        assert Permission.PATIENTS_VIEW in perms
        assert not perms & locked_permissions(frozenset())

    def test_customized_role_is_gated_too(self):
        stored = ["patients.view", "procedures.view", "vaccinations.view"]
        assert granted(Role.NURSE, stored, VACCINATION_ONLY) == {
            Permission.PATIENTS_VIEW, Permission.VACCINATIONS_VIEW,
        }


class TestEntitlements:
    def test_granted_permissions_follow_the_subscription(self):
        seed = seed_clinic()
        uow, tenant = with_modules(seed, VACCINATION_ONLY)
        perms = granted_permissions(uow, tenant, Role.NURSE)
        assert Permission.VACCINATIONS_RECORD in perms
        assert Permission.APPLICATIONS_ADMINISTER not in perms

    def test_matrix_reports_locked_permissions(self):
        seed = seed_clinic()
        uow, _ = with_modules(seed, VACCINATION_ONLY)
        matrix = GetPermissionsMatrix(uow).execute(seed.actor(seed.admin))
        assert "procedures.perform" in matrix.locked
        assert "vaccinations.view" not in matrix.locked

    def test_support_session_is_gated(self):
        seed = seed_clinic()
        with_modules(seed, frozenset())
        session = ImpersonateTenant(seed.factory, FakeTokenIssuer(), FixedClock()).execute(
            PlatformActorContext(admin_id=seed.platform_admin.id), seed.tenant.id, "soporte"
        )
        assert "applications.view" not in session.permissions
        assert "patients.view" in session.permissions


class TestConsultationIndications:
    def _doctor_without_modules(self, seed):
        uow, tenant = with_modules(seed, frozenset())
        perms = granted_permissions(uow, tenant, Role.DOCTOR)
        actor = dataclasses.replace(
            seed.doctor_actor, permissions=frozenset(str(p) for p in perms)
        )
        appt = booked(seed, uow)
        consultation = StartConsultation(uow, FixedClock()).execute(actor, appt.id)
        return uow, actor, consultation

    def test_applications_need_the_module(self):
        seed = seed_clinic()
        uow, actor, consultation = self._doctor_without_modules(seed)
        with pytest.raises(PermissionDenied) as exc:
            AddApplicationDraft(uow, FixedClock()).execute(
                actor, consultation.id,
                ApplicationDraft(drug="Ketorolaco", dose="30 mg",
                                 route=ApplicationRoute.INTRAMUSCULAR),
            )
        assert exc.value.params == {"permission": "applications.view"}

    def test_procedures_need_the_module(self):
        seed = seed_clinic()
        uow, actor, consultation = self._doctor_without_modules(seed)
        with pytest.raises(PermissionDenied):
            AddProcedureDraft(uow, FixedClock()).execute(
                actor, consultation.id, ProcedureTypeId.new(), "Toma de citología"
            )


class TestOnboarding:
    def test_catalog_step_only_with_the_procedures_module(self):
        seed = seed_clinic()
        keys = [s.key for s in GetOnboarding(seed.factory).execute(seed.actor(seed.admin)).steps]
        assert "catalog" in keys
        with_modules(seed, VACCINATION_ONLY)
        keys = [s.key for s in GetOnboarding(seed.factory).execute(seed.actor(seed.admin)).steps]
        assert "catalog" not in keys
