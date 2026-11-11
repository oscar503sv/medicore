"""Domain tests: plan catalog, add-on pricing, subscription status/trial, quotas, quotes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.domain.enums import AddonModule, PlanFeature, Role, SubscriptionStatus
from medicore.domain.services.plan_catalog import (
    CLINICA,
    CLINICA_PLUS,
    EMPRESARIAL,
    INDEPENDIENTE,
    default_addon_pricing,
    default_plans,
)
from medicore.domain.services.seat_usage import seat_usage
from medicore.domain.services.subscription_pricing import monthly_quote
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides, PlanLimits
from medicore.domain.value_objects.subscription import Subscription


def usd(amount: str) -> Money:
    return Money(Decimal(amount), "USD")


def plan(code: str) -> Plan:
    return next(p for p in default_plans() if p.code == code)


ALL = frozenset(AddonModule)
TODAY = date(2026, 11, 10)


class TestCatalog:
    def test_default_catalog_matches_the_published_price_list(self):
        prices = {p.code: p.monthly_price for p in default_plans()}
        assert prices == {
            INDEPENDIENTE: usd("39"), CLINICA: usd("79"), CLINICA_PLUS: usd("119"),
            EMPRESARIAL: None,
        }

    def test_user_permissions_from_clinica_up(self):
        assert not plan(INDEPENDIENTE).has(PlanFeature.USER_PERMISSIONS)
        assert plan(CLINICA).has(PlanFeature.USER_PERMISSIONS)

    def test_update_validates_name_and_price(self):
        p = plan(CLINICA)
        with pytest.raises(InvalidValueObject) as exc:
            p.update(name=" ", monthly_price=usd("79"), limits=p.limits,
                     features=p.features, active=True)
        assert exc.value.code == "plan.name_required"
        with pytest.raises(InvalidValueObject) as exc:
            p.update(name="Clínica", monthly_price=usd("-1"), limits=p.limits,
                     features=p.features, active=True)
        assert exc.value.code == "plan.invalid_price"

    def test_price_must_be_usd(self):
        with pytest.raises(InvalidValueObject):
            Plan(code="x", name="X", monthly_price=Money(Decimal("1"), "EUR"),
                 limits=PlanLimits())


class TestAddonPricing:
    def test_single_modules_add_up(self):
        pricing = default_addon_pricing()
        modules = frozenset({AddonModule.VACCINATION, AddonModule.PROCEDURES})
        assert pricing.monthly_price(modules) == usd("25")

    def test_all_modules_get_the_bundle_price(self):
        assert default_addon_pricing().monthly_price(ALL) == usd("29")

    def test_bundle_above_the_sum_is_not_applied(self):
        pricing = default_addon_pricing()
        pricing.update(pricing.prices, usd("100"))
        assert pricing.monthly_price(ALL) == usd("40")

    def test_every_module_needs_a_price(self):
        with pytest.raises(InvalidValueObject) as exc:
            AddonPricing(prices={AddonModule.VACCINATION: usd("10")}, bundle_price=usd("29"))
        assert exc.value.code == "plan.invalid_price"


class TestLimits:
    def test_negative_limit_rejected(self):
        with pytest.raises(InvalidValueObject) as exc:
            PlanLimits(doctors=-1)
        assert exc.value.code == "plan.invalid_limit"

    def test_overrides_take_precedence_only_where_set(self):
        limits = PlanLimits(doctors=3, support_users=3, locations=1, storage_gb=3)
        merged = limits.overridden_by(LimitOverrides(doctors=5))
        assert merged == PlanLimits(doctors=5, support_users=3, locations=1, storage_gb=3)
        assert limits.overridden_by(None) is limits

    def test_empty_overrides_are_dropped_from_the_subscription(self):
        sub = Subscription(plan_code=CLINICA, limit_overrides=LimitOverrides())
        assert sub.limit_overrides is None


class TestSubscriptionStatus:
    def test_open_ended_is_always_active(self):
        assert Subscription(plan_code=CLINICA).status(TODAY) == SubscriptionStatus.ACTIVE

    def test_paid_period_then_grace_then_read_only(self):
        sub = Subscription(plan_code=CLINICA, period_end=date(2026, 11, 10), grace_days=7)
        assert sub.status(date(2026, 11, 10)) == SubscriptionStatus.ACTIVE
        assert sub.status(date(2026, 11, 11)) == SubscriptionStatus.GRACE
        assert sub.status(date(2026, 11, 17)) == SubscriptionStatus.GRACE
        assert sub.status(date(2026, 11, 18)) == SubscriptionStatus.READ_ONLY

    def test_trial_gets_no_grace(self):
        sub = Subscription(plan_code=CLINICA).start_trial(TODAY)
        assert sub.is_trial and sub.period_end == date(2026, 11, 16)  # 7 days incl. today
        assert sub.status(date(2026, 11, 16)) == SubscriptionStatus.TRIAL
        assert sub.status(date(2026, 11, 17)) == SubscriptionStatus.READ_ONLY

    def test_days_left(self):
        sub = Subscription(plan_code=CLINICA, period_end=date(2026, 11, 15))
        assert sub.days_left(TODAY) == 5
        assert sub.days_left(date(2026, 11, 20)) == -5
        assert Subscription(plan_code=CLINICA).days_left(TODAY) is None

    @pytest.mark.parametrize(
        ("kwargs", "code"),
        [
            ({"plan_code": ""}, "plan.required"),
            ({"plan_code": CLINICA, "grace_days": -1}, "plan.invalid_grace"),
            ({"plan_code": CLINICA, "price_override": usd("-5")}, "plan.invalid_price"),
        ],
    )
    def test_invalid_subscription(self, kwargs, code):
        with pytest.raises(InvalidValueObject) as exc:
            Subscription(**kwargs)
        assert exc.value.code == code

    def test_trial_needs_at_least_one_day(self):
        with pytest.raises(InvalidValueObject) as exc:
            Subscription(plan_code=CLINICA).start_trial(TODAY, 0)
        assert exc.value.code == "plan.invalid_trial"


class TestSeatUsage:
    def test_first_admin_is_free_extra_admins_are_support(self):
        usage = seat_usage(
            {Role.ADMIN: 2, Role.DOCTOR: 3, Role.NURSE: 1, Role.RECEPTIONIST: 2}
        )
        assert (usage.doctors, usage.support_users) == (3, 4)

    def test_lone_admin_uses_no_seat(self):
        assert seat_usage({Role.ADMIN: 1}).support_users == 0


class TestQuote:
    def test_plan_plus_modules(self):
        sub = Subscription(plan_code=CLINICA, modules=frozenset({AddonModule.VACCINATION}))
        assert monthly_quote(sub, plan(CLINICA), default_addon_pricing()) == usd("89")

    def test_plan_plus_bundle(self):
        sub = Subscription(plan_code=CLINICA_PLUS, modules=ALL)
        assert monthly_quote(sub, plan(CLINICA_PLUS), default_addon_pricing()) == usd("148")

    def test_custom_quote_plan_without_agreed_price(self):
        sub = Subscription(plan_code=EMPRESARIAL)
        assert monthly_quote(sub, plan(EMPRESARIAL), default_addon_pricing()) is None

    def test_price_override_replaces_the_total(self):
        sub = Subscription(plan_code=EMPRESARIAL, modules=ALL, price_override=usd("250"))
        assert monthly_quote(sub, plan(EMPRESARIAL), default_addon_pricing()) == usd("250")
