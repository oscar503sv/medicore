"""Platform console · Business overview: revenue, standing, expirations, adoption, seats."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import PlatformActorContext
from medicore.application.use_cases.business import (
    COMPLIMENTARY,
    SUSPENDED,
    TREND_WEEKS,
    GetBusinessOverview,
)
from medicore.domain.entities.subscription_payment import SubscriptionPayment
from medicore.domain.enums import AddonModule, PaymentMethod, TenantStatus
from medicore.domain.services.plan_catalog import CLINICA, CLINICA_PLUS, INDEPENDIENTE
from medicore.domain.shared.identifiers import SubscriptionPaymentId
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import build_tenant, seed_clinic
from tests.support.fakes import FixedClock

NOW = datetime(2026, 5, 31, 9, 0)
TODAY = NOW.date()


def usd(amount: str) -> Money:
    return Money(Decimal(amount), "USD")


def _add(seed, slug: str, sub: Subscription, status=TenantStatus.ACTIVE):
    tenant = build_tenant(slug, subscription=sub)
    tenant.status = status
    seed.factory.store.tenants[tenant.id.value] = tenant
    return tenant


def _pay(seed, tenant, amount: str, paid_on: date):
    payment = SubscriptionPayment(
        id=SubscriptionPaymentId.new(), tenant_id=tenant.id, amount=usd(amount),
        paid_on=paid_on, months=1, plan_code=tenant.subscription.plan_code,
        period_end=paid_on + timedelta(days=30), method=PaymentMethod.BANK_TRANSFER,
        recorded_by=seed.platform_admin.id, recorded_at=NOW,
    )
    seed.factory.store.subscription_payments[payment.id.value] = payment


def _overview(seed):
    actor = PlatformActorContext(admin_id=seed.platform_admin.id)
    return GetBusinessOverview(seed.factory, FixedClock(NOW)).execute(actor)


def _row(dto, slug):
    return next(r for r in dto.clinics if r.slug == slug)


def test_mrr_counts_only_paying_clinics():
    seed = seed_clinic()  # open-ended, like the public demo: complimentary
    _add(seed, "pagando", Subscription(
        plan_code=CLINICA, modules=frozenset({AddonModule.VACCINATION}),
        period_end=TODAY + timedelta(days=40),
    ))
    _add(seed, "en-gracia", Subscription(plan_code=INDEPENDIENTE, period_end=TODAY - timedelta(2)))
    _add(seed, "prueba", Subscription(plan_code=CLINICA_PLUS).start_trial(TODAY))
    _add(seed, "especial", Subscription(
        plan_code=CLINICA_PLUS, period_end=TODAY + timedelta(days=90), price_override=usd("100"),
    ))
    _add(seed, "suspendida", Subscription(plan_code=CLINICA, period_end=TODAY + timedelta(9)),
         status=TenantStatus.SUSPENDED)

    dto = _overview(seed)

    # Clínica 79 + vaccination 10, Independiente 39 (in grace, still paying), special 100.
    assert dto.mrr == usd("228")
    assert _row(dto, "clinica-norte").standing == COMPLIMENTARY
    assert _row(dto, "prueba").paying is False
    assert _row(dto, "suspendida").standing == SUSPENDED
    assert dto.by_standing == {
        COMPLIMENTARY: 1, "active": 2, "grace": 1, "trial": 1, SUSPENDED: 1,
    }
    assert {p.code: (p.clinics, p.mrr) for p in dto.by_plan}[CLINICA] == (2, usd("89"))
    assert dto.by_module[str(AddonModule.VACCINATION)] == 2  # seed has every module


def test_expiring_lists_what_needs_renewing_soonest_first():
    seed = seed_clinic()
    _add(seed, "en-gracia", Subscription(plan_code=CLINICA, period_end=TODAY - timedelta(2)))
    _add(seed, "pronto", Subscription(plan_code=CLINICA, period_end=TODAY + timedelta(5)))
    _add(seed, "lejos", Subscription(plan_code=CLINICA, period_end=TODAY + timedelta(60)))
    _add(seed, "vencida", Subscription(plan_code=CLINICA, period_end=TODAY - timedelta(30)))

    assert [r.slug for r in _overview(seed).expiring] == ["en-gracia", "pronto"]


def test_collected_this_and_last_month():
    seed = seed_clinic()
    tenant = _add(seed, "pagando", Subscription(plan_code=CLINICA, period_end=TODAY))
    _pay(seed, tenant, "79", date(2026, 5, 3))
    _pay(seed, tenant, "89", date(2026, 5, 28))
    _pay(seed, tenant, "79", date(2026, 4, 2))
    _pay(seed, tenant, "50", date(2026, 3, 30))  # older: not shown

    dto = _overview(seed)
    assert dto.collected_this_month == usd("168")
    assert dto.collected_last_month == usd("79")


def test_seats_at_capacity():
    seed = seed_clinic()  # 1 doctor, nurse + receptionist as support, 1 site
    uow = seed.factory.for_tenant(seed.tenant.id)
    tenant = uow.tenants.get_by_id(seed.tenant.id)
    tenant.subscription = Subscription(
        plan_code=CLINICA, period_end=TODAY + timedelta(40),
        limit_overrides=LimitOverrides(doctors=1),
    )
    uow.tenants.save(tenant)

    row = _row(_overview(seed), "clinica-norte")
    assert row.usage == {"doctors": 1, "support_users": 2, "locations": 1}
    assert row.at_capacity == ("doctors", "locations")


def test_adoption_from_the_audit_trail():
    seed = seed_clinic()
    _add(seed, "quieta", Subscription(plan_code=CLINICA, period_end=TODAY + timedelta(9)))
    store = seed.factory.store
    for user, when in ((seed.doctor, NOW - timedelta(days=1)), (seed.nurse, NOW - timedelta(2)),
                       (seed.doctor, NOW - timedelta(days=20))):
        entry = audit_entry(seed.actor(user), when, "auth.login", "User", str(user.id))
        store.audit[entry.id.value] = entry

    dto = _overview(seed)
    busy = _row(dto, "clinica-norte").activity
    assert busy.active_users == 2
    assert busy.last_activity == NOW - timedelta(days=1)
    assert _row(dto, "quieta").activity.last_activity is None
    assert (dto.active_clinics, dto.inactive_clinics) == (1, 1)


def test_weekly_trend_has_every_week():
    dto = _overview(seed_clinic())
    assert len(dto.weekly_signed) == TREND_WEEKS
    assert dto.weekly_signed[-1][0] == TODAY - timedelta(days=TODAY.weekday())
    assert all(count == 0 for _, count in dto.weekly_signed)
