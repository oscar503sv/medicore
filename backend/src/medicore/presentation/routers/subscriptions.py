"""Subscriptions router: the plan catalog and each clinic's subscription (platform console),
plus the clinic's own read-only view of its plan."""

from __future__ import annotations

from fastapi import APIRouter

from medicore.application.use_cases.subscriptions import (
    GetCatalog,
    GetMyPayments,
    GetMySubscription,
    GetSubscriptionNotice,
    GetTenantSubscription,
    ListTenantPayments,
    RecordPayment,
    RecordPaymentCommand,
    StartTrial,
    SubscriptionCommand,
    UpdateAddonPricing,
    UpdatePlan,
    UpdatePlanCommand,
    UpdateTenantSubscription,
)
from medicore.domain.shared.identifiers import TenantId
from medicore.domain.value_objects.plan_limits import LimitOverrides, PlanLimits
from medicore.presentation.dependencies import Actor, Clock, PlatformActor, UoW, UoWFactory
from medicore.presentation.schemas.subscriptions import (
    AddonPricingResponse,
    CatalogResponse,
    PaymentRecordedResponse,
    PaymentResponse,
    PlanResponse,
    RecordPaymentRequest,
    StartTrialRequest,
    SubscriptionNoticeResponse,
    SubscriptionRequest,
    SubscriptionResponse,
    UpdateAddonPricingRequest,
    UpdatePlanRequest,
)
from medicore.presentation.serializers import (
    ser_addon_pricing,
    ser_payment,
    ser_plan,
    ser_subscription,
    ser_subscription_notice,
)

router = APIRouter(tags=["subscriptions"])


# ── Catalog (platform) ────────────────────────────────────────────────────────


@router.get("/platform/plans", response_model=CatalogResponse)
def get_catalog(actor: PlatformActor, factory: UoWFactory):
    catalog = GetCatalog(factory).execute(actor)
    return {
        "plans": [ser_plan(p) for p in catalog.plans],
        "addons": ser_addon_pricing(catalog.addons),
    }


@router.put("/platform/plans/{code}", response_model=PlanResponse)
def update_plan(
    code: str, body: UpdatePlanRequest, actor: PlatformActor, factory: UoWFactory, clock: Clock
):
    cmd = UpdatePlanCommand(
        name=body.name,
        monthly_price=body.monthly_price,
        limits=PlanLimits(**body.limits.model_dump()),
        features=frozenset(body.features),
        active=body.active,
    )
    return ser_plan(UpdatePlan(factory, clock).execute(actor, code, cmd))


@router.put("/platform/addon-pricing", response_model=AddonPricingResponse)
def update_addon_pricing(
    body: UpdateAddonPricingRequest, actor: PlatformActor, factory: UoWFactory, clock: Clock
):
    pricing = UpdateAddonPricing(factory, clock).execute(actor, body.prices, body.bundle_price)
    return ser_addon_pricing(pricing)


# ── A clinic's subscription (platform) ────────────────────────────────────────


@router.get("/platform/tenants/{tenant_id}/subscription", response_model=SubscriptionResponse)
def get_tenant_subscription(
    tenant_id: str, actor: PlatformActor, factory: UoWFactory, clock: Clock
):
    view = GetTenantSubscription(factory, clock).execute(actor, TenantId.parse(tenant_id))
    return ser_subscription(view)


@router.put("/platform/tenants/{tenant_id}/subscription", response_model=SubscriptionResponse)
def update_tenant_subscription(
    tenant_id: str,
    body: SubscriptionRequest,
    actor: PlatformActor,
    factory: UoWFactory,
    clock: Clock,
):
    overrides = (
        LimitOverrides(**body.limit_overrides.model_dump()) if body.limit_overrides else None
    )
    cmd = SubscriptionCommand(
        plan_code=body.plan_code,
        modules=frozenset(body.modules),
        period_end=body.period_end,
        is_trial=body.is_trial,
        grace_days=body.grace_days,
        limit_overrides=overrides if overrides and not overrides.is_empty else None,
        price_override=body.price_override,
    )
    view = UpdateTenantSubscription(factory, clock).execute(actor, TenantId.parse(tenant_id), cmd)
    return ser_subscription(view)


@router.post(
    "/platform/tenants/{tenant_id}/subscription/trial", response_model=SubscriptionResponse
)
def start_trial(
    tenant_id: str,
    body: StartTrialRequest,
    actor: PlatformActor,
    factory: UoWFactory,
    clock: Clock,
):
    view = StartTrial(factory, clock).execute(actor, TenantId.parse(tenant_id), body.days)
    return ser_subscription(view)


@router.get("/platform/tenants/{tenant_id}/payments", response_model=list[PaymentResponse])
def list_tenant_payments(tenant_id: str, actor: PlatformActor, factory: UoWFactory):
    payments = ListTenantPayments(factory).execute(actor, TenantId.parse(tenant_id))
    return [ser_payment(p) for p in payments]


@router.post(
    "/platform/tenants/{tenant_id}/payments",
    response_model=PaymentRecordedResponse,
    status_code=201,
)
def record_payment(
    tenant_id: str,
    body: RecordPaymentRequest,
    actor: PlatformActor,
    factory: UoWFactory,
    clock: Clock,
):
    cmd = RecordPaymentCommand(
        amount=body.amount,
        paid_on=body.paid_on,
        months=body.months,
        method=body.method,
        reference=body.reference,
        notes=body.notes,
    )
    result = RecordPayment(factory, clock).execute(actor, TenantId.parse(tenant_id), cmd)
    return {"payment": ser_payment(result.payment), "subscription": ser_subscription(result.view)}


# ── The clinic's own plan ─────────────────────────────────────────────────────


@router.get("/organization/subscription", response_model=SubscriptionResponse)
def get_my_subscription(actor: Actor, uow: UoW, clock: Clock):
    return ser_subscription(GetMySubscription(uow, clock).execute(actor))


@router.get("/organization/subscription/payments", response_model=list[PaymentResponse])
def get_my_payments(actor: Actor, uow: UoW):
    return [ser_payment(p) for p in GetMyPayments(uow).execute(actor)]


@router.get("/auth/me/subscription", response_model=SubscriptionNoticeResponse)
def get_subscription_notice(actor: Actor, uow: UoW, clock: Clock):
    """Any user: the subscription status for the app banner (no prices or limits)."""
    return ser_subscription_notice(GetSubscriptionNotice(uow, clock).execute(actor))
