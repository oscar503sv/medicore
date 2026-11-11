"""ORM models for the subscription catalog (platform-level) and clinic payments."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class PlanModel(Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # USD; NULL = custom quote per subscription.
    monthly_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # NULL = unlimited.
    limit_doctors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_support_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_locations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_storage_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analytics_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="basic", server_default="basic"
    )


class AddonPricingModel(Base):
    __tablename__ = "addon_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    # {"vaccination": "10.00", ...} in USD.
    prices: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    bundle_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class SubscriptionPaymentModel(Base):
    __tablename__ = "subscription_payments"
    __table_args__ = (Index("ix_subscription_payments_tenant", "tenant_id", "paid_on"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # USD
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    months: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_code: Mapped[str] = mapped_column(String(30), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
