"""Subscription schemas: plan catalog, add-on prices and a clinic's subscription.

Money travels as a decimal string ("39.00", USD) so no amount goes through a float.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from medicore.domain.enums import AddonModule, PaymentMethod, PlanFeature
from medicore.domain.value_objects.subscription import MAX_RENEWAL_MONTHS

Price = Decimal  # input: number or numeric string, validated non-negative where used


class PlanLimitsSchema(BaseModel):
    """``null`` means unlimited on a plan, and "use the plan's" on a clinic override."""

    doctors: int | None = Field(default=None, ge=0)
    support_users: int | None = Field(default=None, ge=0)
    locations: int | None = Field(default=None, ge=0)
    storage_gb: int | None = Field(default=None, ge=0)


class PlanResponse(BaseModel):
    code: str
    name: str
    monthly_price: str | None  # null: custom quote
    limits: PlanLimitsSchema
    features: list[str]
    active: bool
    sort_order: int


class AddonPricingResponse(BaseModel):
    prices: dict[str, str]
    bundle_price: str


class CatalogResponse(BaseModel):
    plans: list[PlanResponse]
    addons: AddonPricingResponse


class UpdatePlanRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    monthly_price: Price | None = Field(default=None, ge=0)
    limits: PlanLimitsSchema
    features: list[PlanFeature] = []
    active: bool = True


class UpdateAddonPricingRequest(BaseModel):
    prices: dict[AddonModule, Price]
    bundle_price: Price = Field(ge=0)


class SubscriptionRequest(BaseModel):
    plan_code: str
    modules: list[AddonModule] = []
    period_end: date | None = None  # null: no expiry (courtesy / demo)
    is_trial: bool = False
    grace_days: int = Field(default=7, ge=0, le=60)
    limit_overrides: PlanLimitsSchema | None = None
    price_override: Price | None = Field(default=None, ge=0)


class StartTrialRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=90)


class SeatUsageResponse(BaseModel):
    doctors: int
    support_users: int
    locations: int


class SubscriptionResponse(BaseModel):
    plan: PlanResponse
    modules: list[str]
    period_end: date | None
    is_trial: bool
    grace_days: int
    status: str
    today: date
    days_left: int | None
    limits: PlanLimitsSchema  # effective: plan quotas with the overrides applied
    limit_overrides: PlanLimitsSchema | None
    price_override: str | None
    monthly_price: str | None
    usage: SeatUsageResponse
    addon_prices: AddonPricingResponse


class TenantSubscriptionSummary(BaseModel):
    """What the clinic list needs at a glance."""

    plan_code: str
    modules: list[str]
    period_end: date | None
    is_trial: bool
    status: str
    days_left: int | None


class RecordPaymentRequest(BaseModel):
    amount: Price = Field(ge=0)
    paid_on: date
    months: int = Field(ge=1, le=MAX_RENEWAL_MONTHS)
    method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class PaymentResponse(BaseModel):
    id: str
    amount: str
    paid_on: date
    months: int
    plan_code: str
    period_end: date
    method: str
    reference: str | None
    notes: str | None
    recorded_at: datetime


class PaymentRecordedResponse(BaseModel):
    payment: PaymentResponse
    subscription: SubscriptionResponse


class SubscriptionNoticeResponse(BaseModel):
    status: str
    is_trial: bool
    period_end: date | None
    grace_until: date | None
    days_left: int | None
