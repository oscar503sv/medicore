"""Domain tests: plan catalog, add-on pricing, subscription status/trial, quotas, quotes."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.domain.entities.subscription_payment import SubscriptionPayment
from medicore.domain.enums import (
    CLINICAL_MODULES,
    AddonModule,
    AnalyticsTier,
    PaymentMethod,
    PlanFeature,
    Role,
    SubscriptionStatus,
)
from medicore.domain.services.analytics_access import addon_adds_nothing, analytics_tier
from medicore.domain.services.plan_catalog import (
    CLINICA,
    CLINICA_PLUS,
    EMPRESARIAL,
    INDEPENDIENTE,
    default_addon_pricing,
    default_plans,
)
from medicore.domain.services.seat_usage import (
    QUOTA_DOCTORS,
    check_quota,
    ensure_seats,
    seat_usage,
)
from medicore.domain.services.subscription_pricing import monthly_quote
from medicore.domain.shared.errors import InvalidValueObject, QuotaExceeded
from medicore.domain.shared.identifiers import PlatformAdminId, SubscriptionPaymentId, TenantId
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides, PlanLimits
from medicore.domain.value_objects.subscription import Subscription, add_months


def usd(amount: str) -> Money:
    return Money(Decimal(amount), "USD")


def plan(code: str) -> Plan:
    return next(p for p in default_plans() if p.code == code)


ALL = CLINICAL_MODULES
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

    def test_analytics_is_charged_apart_from_the_bundle(self):
        pricing = default_addon_pricing()
        assert pricing.monthly_price(frozenset(AddonModule)) == usd("49")
        assert pricing.monthly_price(frozenset({AddonModule.ANALYTICS})) == usd("20")

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


class TestAnalyticsTier:
    def test_tiers_per_published_plan(self):
        assert {p.code: p.analytics_tier for p in default_plans()} == {
            INDEPENDIENTE: AnalyticsTier.BASIC, CLINICA: AnalyticsTier.CLINIC,
            CLINICA_PLUS: AnalyticsTier.OPERATIONS, EMPRESARIAL: AnalyticsTier.OPERATIONS,
        }

    def test_tiers_are_ordered(self):
        assert AnalyticsTier.OPERATIONS.includes(AnalyticsTier.CLINIC)
        assert AnalyticsTier.CLINIC.includes(AnalyticsTier.CLINIC)
        assert not AnalyticsTier.BASIC.includes(AnalyticsTier.CLINIC)

    @pytest.mark.parametrize("code", [INDEPENDIENTE, CLINICA])
    def test_addon_raises_to_operations(self, code):
        sub = Subscription(plan_code=code, modules=frozenset({AddonModule.ANALYTICS}))
        assert analytics_tier(plan(code), sub) == AnalyticsTier.OPERATIONS
        assert not addon_adds_nothing(plan(code))

    def test_without_addon_the_plan_decides(self):
        sub = Subscription(plan_code=CLINICA, modules=CLINICAL_MODULES)
        assert analytics_tier(plan(CLINICA), sub) == AnalyticsTier.CLINIC

    def test_operations_plans_gain_nothing_from_the_addon(self):
        assert addon_adds_nothing(plan(CLINICA_PLUS))
        assert addon_adds_nothing(plan(EMPRESARIAL))

    def test_update_keeps_the_tier_unless_given(self):
        p = plan(CLINICA)
        p.update(name="Clínica", monthly_price=usd("79"), limits=p.limits,
                 features=p.features, active=True)
        assert p.analytics_tier == AnalyticsTier.CLINIC
        p.update(name="Clínica", monthly_price=usd("79"), limits=p.limits,
                 features=p.features, active=True, analytics_tier=AnalyticsTier.BASIC)
        assert p.analytics_tier == AnalyticsTier.BASIC


class TestQuote:
    def test_plan_plus_modules(self):
        sub = Subscription(plan_code=CLINICA, modules=frozenset({AddonModule.VACCINATION}))
        assert monthly_quote(sub, plan(CLINICA), default_addon_pricing()) == usd("89")

    def test_plan_plus_bundle(self):
        sub = Subscription(plan_code=CLINICA_PLUS, modules=ALL)
        assert monthly_quote(sub, plan(CLINICA_PLUS), default_addon_pricing()) == usd("148")

    def test_plan_plus_bundle_and_analytics(self):
        sub = Subscription(plan_code=CLINICA, modules=frozenset(AddonModule))
        assert monthly_quote(sub, plan(CLINICA), default_addon_pricing()) == usd("128")

    def test_custom_quote_plan_without_agreed_price(self):
        sub = Subscription(plan_code=EMPRESARIAL)
        assert monthly_quote(sub, plan(EMPRESARIAL), default_addon_pricing()) is None

    def test_price_override_replaces_the_total(self):
        sub = Subscription(plan_code=EMPRESARIAL, modules=ALL, price_override=usd("250"))
        assert monthly_quote(sub, plan(EMPRESARIAL), default_addon_pricing()) == usd("250")


class TestQuotaRule:
    def test_growing_past_the_limit_is_refused(self):
        with pytest.raises(QuotaExceeded) as exc:
            check_quota(QUOTA_DOCTORS, 3, 3, 4)
        assert (exc.value.code, exc.value.params) == ("plan.quota_doctors", {"limit": 3})

    def test_up_to_the_limit_is_fine(self):
        check_quota(QUOTA_DOCTORS, 3, 2, 3)

    def test_unlimited(self):
        check_quota(QUOTA_DOCTORS, None, 99, 100)

    def test_a_clinic_over_its_limit_keeps_what_it_has(self):
        # e.g. after moving to a smaller plan: a change that doesn't grow usage passes
        check_quota(QUOTA_DOCTORS, 1, 3, 3)
        check_quota(QUOTA_DOCTORS, 1, 3, 2)

    def test_seats_check_each_quota(self):
        limits = PlanLimits(doctors=3, support_users=1)
        before = seat_usage({Role.ADMIN: 1, Role.NURSE: 1})
        with pytest.raises(QuotaExceeded) as exc:
            ensure_seats(limits, before, seat_usage({Role.ADMIN: 2, Role.NURSE: 1}))
        assert exc.value.code == "plan.quota_support_users"


class TestRenewal:
    def test_add_months_clamps_to_the_month_end(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
        assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)

    def test_up_to_date_clinic_continues_from_its_paid_until(self):
        sub = Subscription(plan_code=CLINICA, period_end=date(2026, 11, 30))
        assert sub.renew(TODAY, 1).period_end == date(2026, 12, 30)

    def test_clinic_in_grace_continues_from_its_paid_until(self):
        sub = Subscription(plan_code=CLINICA, period_end=date(2026, 11, 5), grace_days=7)
        assert sub.status(TODAY) == SubscriptionStatus.GRACE
        assert sub.renew(TODAY, 1).period_end == date(2026, 12, 5)

    def test_lapsed_clinic_starts_from_today(self):
        sub = Subscription(plan_code=CLINICA, period_end=date(2026, 9, 30), grace_days=7)
        assert sub.renew(TODAY, 1).period_end == date(2026, 12, 9)  # 10 nov → 9 dic

    def test_paying_during_a_trial_leaves_the_trial(self):
        sub = Subscription(plan_code=CLINICA).start_trial(TODAY)  # until 16 nov
        renewed = sub.renew(TODAY, 1)
        assert (renewed.is_trial, renewed.period_end) == (False, date(2026, 12, 16))

    def test_open_ended_starts_from_today(self):
        assert Subscription(plan_code=CLINICA).renew(TODAY, 12).period_end == date(2027, 11, 9)

    def test_months_are_bounded(self):
        with pytest.raises(InvalidValueObject) as exc:
            Subscription(plan_code=CLINICA).renew(TODAY, 0)
        assert exc.value.code == "payment.invalid_months"

    def test_grace_until(self):
        assert Subscription(plan_code=CLINICA, period_end=TODAY, grace_days=7).grace_until == (
            date(2026, 11, 17)
        )
        assert Subscription(plan_code=CLINICA).start_trial(TODAY).grace_until == date(2026, 11, 16)
        assert Subscription(plan_code=CLINICA).grace_until is None


class TestPayment:
    def _payment(self, **kw):
        defaults = dict(
            id=SubscriptionPaymentId.new(), tenant_id=TenantId.new(), amount=usd("79"),
            paid_on=TODAY, months=1, plan_code=CLINICA, period_end=date(2026, 12, 9),
            method=PaymentMethod.BANK_TRANSFER, recorded_by=PlatformAdminId.new(),
            recorded_at=datetime(2026, 11, 10, 12, 0),
        )
        return SubscriptionPayment(**(defaults | kw))

    def test_valid_payment(self):
        assert self._payment().amount == usd("79")

    @pytest.mark.parametrize(
        ("kw", "code"),
        [
            ({"amount": usd("-1")}, "payment.invalid_amount"),
            ({"amount": Money(Decimal("79"), "EUR")}, "payment.invalid_amount"),
            ({"months": 0}, "payment.invalid_months"),
        ],
    )
    def test_invalid_payment(self, kw, code):
        with pytest.raises(InvalidValueObject) as exc:
            self._payment(**kw)
        assert exc.value.code == code
