"""Integration tests: plan catalog, add-on pricing and a clinic's subscription round-trip
through PostgreSQL (the catalog rows are seeded by the subscriptions migration).

Same harness as the other SQL tests: TEST_DATABASE_URL (or DATABASE_URL from settings),
one outer transaction rolled back at the end, and SKIP when PostgreSQL is unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.subscription_payment import SubscriptionPayment
from medicore.domain.enums import AddonModule, AnalyticsTier, PaymentMethod
from medicore.domain.services.plan_catalog import (
    CLINICA,
    EMPRESARIAL,
    default_addon_pricing,
    default_plans,
)
from medicore.domain.shared.identifiers import PlatformAdminId, SubscriptionPaymentId
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.plan_limits import LimitOverrides
from medicore.domain.value_objects.subscription import Subscription
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.repositories.subscription import (
    SqlAddonPricingRepository,
    SqlPlanRepository,
    SqlSubscriptionPaymentRepository,
)
from medicore.infrastructure.persistence.repositories.tenant import SqlTenantRepository
from tests.support.builders import build_tenant


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("PostgreSQL not available")
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    yield session
    session.close()
    trans.rollback()
    connection.close()


def usd(amount: str) -> Money:
    return Money(Decimal(amount), "USD")


def test_migration_seeds_the_default_catalog(session):
    stored = {p.code: p for p in SqlPlanRepository(session).list()}
    for plan in default_plans():
        assert stored[plan.code].monthly_price == plan.monthly_price
        assert stored[plan.code].limits == plan.limits
        assert stored[plan.code].features == plan.features
        assert stored[plan.code].analytics_tier == plan.analytics_tier
    pricing = SqlAddonPricingRepository(session).get()
    assert pricing.prices == default_addon_pricing().prices
    assert pricing.bundle_price == usd("29")


def test_plan_update_round_trips(session):
    repo = SqlPlanRepository(session)
    plan = repo.get(CLINICA)
    plan.update(name="Clínica 2", monthly_price=usd("85.50"), limits=plan.limits,
                features=plan.features, active=False, analytics_tier=AnalyticsTier.OPERATIONS)
    repo.save(plan)
    session.flush()
    session.expire_all()
    stored = repo.get(CLINICA)
    assert (stored.name, stored.monthly_price, stored.active) == ("Clínica 2", usd("85.50"), False)
    assert stored.analytics_tier == AnalyticsTier.OPERATIONS
    assert CLINICA not in [p.code for p in repo.list(include_inactive=False)]


def test_addon_pricing_round_trips(session):
    repo = SqlAddonPricingRepository(session)
    pricing = repo.get()
    pricing.update({m: usd("11") for m in AddonModule}, usd("30"))
    repo.save(pricing)
    session.flush()
    session.expire_all()
    assert repo.get().price_of(AddonModule.PROCEDURES) == usd("11")
    assert repo.get().bundle_price == usd("30")


def test_tenant_subscription_round_trips(session):
    sub = Subscription(
        plan_code=EMPRESARIAL,
        modules=frozenset({AddonModule.VACCINATION, AddonModule.PROCEDURES}),
        period_end=date(2026, 12, 31),
        is_trial=False,
        grace_days=10,
        limit_overrides=LimitOverrides(doctors=12, storage_gb=50),
        price_override=usd("250"),
    )
    tenant = build_tenant(f"sub-{uuid.uuid4().hex[:10]}", subscription=sub)
    repo = SqlTenantRepository(session)
    repo.save(tenant)
    session.flush()
    session.expire_all()
    assert repo.get_by_id(tenant.id).subscription == sub


def test_trial_subscription_round_trips(session):
    sub = Subscription(plan_code=CLINICA).start_trial(date(2026, 11, 10))
    tenant = build_tenant(f"sub-{uuid.uuid4().hex[:10]}", subscription=sub)
    repo = SqlTenantRepository(session)
    repo.save(tenant)
    session.flush()
    session.expire_all()
    stored = repo.get_by_id(tenant.id).subscription
    assert stored == sub and stored.limit_overrides is None and stored.price_override is None


def test_payments_round_trip_newest_first(session):
    tenant = build_tenant(f"pay-{uuid.uuid4().hex[:10]}")
    SqlTenantRepository(session).save(tenant)
    session.flush()
    repo = SqlSubscriptionPaymentRepository(session, tenant.id)

    def payment(paid_on: date, reference: str) -> SubscriptionPayment:
        return SubscriptionPayment(
            id=SubscriptionPaymentId.new(), tenant_id=tenant.id, amount=usd("79.50"),
            paid_on=paid_on, months=1, plan_code=CLINICA, period_end=date(2026, 12, 31),
            method=PaymentMethod.BANK_TRANSFER, recorded_by=PlatformAdminId.new(),
            recorded_at=datetime(2026, 11, 10, 12, 0, tzinfo=UTC), reference=reference,
        )

    older, newer = payment(date(2026, 10, 1), "A"), payment(date(2026, 11, 1), "B")
    repo.save(older)
    repo.save(newer)
    session.flush()
    session.expire_all()
    assert repo.list() == [newer, older]
    other = SqlSubscriptionPaymentRepository(session, build_tenant("x-unused").id)
    assert other.list() == []
