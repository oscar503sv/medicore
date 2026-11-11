"""Use-case tests: plan catalog edits and each clinic's subscription."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from medicore.application.common.context import PlatformActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.use_cases.platform import CreateTenantCommand, CreateTenantWithAdmin
from medicore.application.use_cases.subscriptions import (
    GetCatalog,
    GetMySubscription,
    GetTenantSubscription,
    StartTrial,
    SubscriptionCommand,
    UpdateAddonPricing,
    UpdatePlan,
    UpdatePlanCommand,
    UpdateTenantSubscription,
)
from medicore.domain.enums import AddonModule, PlanFeature, SubscriptionStatus
from medicore.domain.services.plan_catalog import CLINICA, CLINICA_PLUS, EMPRESARIAL
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides, PlanLimits
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, PlainPasswordHasher

# FixedClock is 2026-05-31 09:00 (naive UTC); the seed clinic's timezone keeps that date.
TODAY = date(2026, 5, 31)


def actor_for(seed) -> PlatformActorContext:
    return PlatformActorContext(admin_id=seed.platform_admin.id)


def command(plan_code=CLINICA, **kwargs) -> SubscriptionCommand:
    defaults = dict(
        modules=frozenset(), period_end=date(2026, 6, 30), is_trial=False, grace_days=7
    )
    return SubscriptionCommand(plan_code=plan_code, **(defaults | kwargs))


def actions(seed) -> list[str]:
    return [e.action for e in seed.factory.platform_uow().platform_audit.list()]


class TestCatalog:
    def test_lists_plans_and_addon_prices(self):
        seed = seed_clinic()
        catalog = GetCatalog(seed.factory).execute(actor_for(seed))
        assert [p.code for p in catalog.plans][:2] == ["independiente", CLINICA]
        assert catalog.addons.bundle_price.amount == Decimal("29")

    def test_update_plan_changes_price_and_limits_and_is_audited(self):
        seed = seed_clinic()
        plan = UpdatePlan(seed.factory, FixedClock()).execute(
            actor_for(seed),
            CLINICA,
            UpdatePlanCommand(
                name="Clínica", monthly_price=Decimal("85"),
                limits=PlanLimits(doctors=4, support_users=3, locations=1, storage_gb=3),
                features=frozenset({PlanFeature.USER_PERMISSIONS}), active=True,
            ),
        )
        assert plan.monthly_price == Money(Decimal("85"), "USD")
        stored = seed.factory.platform_uow().plans.get(CLINICA)
        assert stored.limits.doctors == 4
        assert "plan.updated" in actions(seed)

    def test_update_unknown_plan(self):
        seed = seed_clinic()
        with pytest.raises(EntityNotFound):
            UpdatePlan(seed.factory, FixedClock()).execute(
                actor_for(seed), "nope",
                UpdatePlanCommand(name="X", monthly_price=None, limits=PlanLimits(),
                                  features=frozenset(), active=True),
            )

    def test_update_addon_pricing(self):
        seed = seed_clinic()
        prices = {m: Decimal("12") for m in AddonModule}
        pricing = UpdateAddonPricing(seed.factory, FixedClock()).execute(
            actor_for(seed), prices, Decimal("30")
        )
        assert pricing.bundle_price.amount == Decimal("30")
        assert seed.factory.platform_uow().addon_pricing.get().price_of(
            AddonModule.VACCINATION
        ).amount == Decimal("12")
        assert "addon_pricing.updated" in actions(seed)


class TestTenantSubscription:
    def test_view_resolves_plan_usage_and_price(self):
        seed = seed_clinic()  # Clínica Plus, every module, no expiry
        view = GetTenantSubscription(seed.factory, FixedClock()).execute(
            actor_for(seed), seed.tenant.id
        )
        assert view.plan.code == CLINICA_PLUS
        assert view.status == SubscriptionStatus.ACTIVE
        assert view.days_left is None
        # admin (free), doctor, nurse, receptionist
        assert (view.usage.doctors, view.usage.support_users) == (1, 2)
        assert view.monthly_price == Money(Decimal("148"), "USD")

    def test_update_sets_plan_modules_and_overrides(self):
        seed = seed_clinic()
        view = UpdateTenantSubscription(seed.factory, FixedClock()).execute(
            actor_for(seed),
            seed.tenant.id,
            command(
                modules=frozenset({AddonModule.VACCINATION}),
                limit_overrides=LimitOverrides(doctors=5),
            ),
        )
        assert view.plan.code == CLINICA
        assert view.limits.doctors == 5 and view.limits.support_users == 3
        assert view.days_left == 30
        assert view.monthly_price == Money(Decimal("89"), "USD")
        stored = seed.factory.for_tenant(seed.tenant.id).tenants.get_by_id(seed.tenant.id)
        assert stored.subscription.modules == frozenset({AddonModule.VACCINATION})
        assert "tenant.subscription_updated" in actions(seed)

    def test_inactive_plan_cannot_be_chosen(self):
        seed = seed_clinic()
        platform = seed.factory.platform_uow()
        plan = platform.plans.get(CLINICA)
        plan.active = False
        platform.plans.save(plan)
        with pytest.raises(ValidationError) as exc:
            UpdateTenantSubscription(seed.factory, FixedClock()).execute(
                actor_for(seed), seed.tenant.id, command(CLINICA)
            )
        assert exc.value.code == "plan.unavailable"

    def test_clinic_already_on_an_inactive_plan_can_keep_it(self):
        seed = seed_clinic()
        platform = seed.factory.platform_uow()
        plan = platform.plans.get(CLINICA_PLUS)
        plan.active = False
        platform.plans.save(plan)
        view = UpdateTenantSubscription(seed.factory, FixedClock()).execute(
            actor_for(seed), seed.tenant.id, command(CLINICA_PLUS)
        )
        assert view.plan.code == CLINICA_PLUS

    def test_custom_price_for_empresarial(self):
        seed = seed_clinic()
        view = UpdateTenantSubscription(seed.factory, FixedClock()).execute(
            actor_for(seed), seed.tenant.id,
            command(EMPRESARIAL, price_override=Decimal("250")),
        )
        assert view.monthly_price == Money(Decimal("250"), "USD")
        assert view.limits.doctors is None  # unlimited

    def test_start_trial(self):
        seed = seed_clinic()
        view = StartTrial(seed.factory, FixedClock()).execute(actor_for(seed), seed.tenant.id)
        assert view.status == SubscriptionStatus.TRIAL
        assert view.subscription.period_end == date(2026, 6, 6)
        assert "tenant.trial_started" in actions(seed)

    def test_expired_paid_period_goes_through_grace_to_read_only(self):
        seed = seed_clinic()
        UpdateTenantSubscription(seed.factory, FixedClock()).execute(
            actor_for(seed), seed.tenant.id, command(period_end=date(2026, 5, 20), grace_days=7)
        )
        view = GetTenantSubscription(seed.factory, FixedClock()).execute(
            actor_for(seed), seed.tenant.id
        )
        assert view.status == SubscriptionStatus.READ_ONLY
        assert view.days_left == -11


class TestCreateTenant:
    def _cmd(self, **kwargs) -> CreateTenantCommand:
        return CreateTenantCommand(
            legal_name="Clínica Sur SL", tax_id="B99", slug="clinica-sur",
            timezone="America/El_Salvador", location_name="San Salvador",
            admin_name="Admin Sur", admin_email="admin@sur.test",
            admin_password="temp-pass-123", **kwargs,
        )

    def test_new_clinic_on_trial(self):
        seed = seed_clinic()
        result = CreateTenantWithAdmin(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
            actor_for(seed), self._cmd(subscription=command(period_end=None), trial_days=7)
        )
        sub = result.tenant.subscription
        assert (sub.plan_code, sub.is_trial, sub.period_end) == (CLINICA, True, date(2026, 6, 6))

    def test_new_paid_clinic(self):
        seed = seed_clinic()
        result = CreateTenantWithAdmin(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
            actor_for(seed), self._cmd(subscription=command())
        )
        assert result.tenant.subscription.period_end == date(2026, 6, 30)
        assert not result.tenant.subscription.is_trial

    def test_needs_trial_or_period(self):
        seed = seed_clinic()
        with pytest.raises(ValidationError) as exc:
            CreateTenantWithAdmin(seed.factory, PlainPasswordHasher(), FixedClock()).execute(
                actor_for(seed), self._cmd(subscription=command(period_end=None))
            )
        assert exc.value.code == "plan.period_required"


class TestMySubscription:
    def test_admin_reads_own_plan(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        view = GetMySubscription(uow, FixedClock()).execute(seed.actor(seed.admin))
        assert view.plan.code == CLINICA_PLUS

    def test_doctor_cannot(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            GetMySubscription(uow, FixedClock()).execute(seed.doctor_actor)
