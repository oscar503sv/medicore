"""ORM models for the subscription catalog (platform-level)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
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


class AddonPricingModel(Base):
    __tablename__ = "addon_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    # {"vaccination": "10.00", ...} in USD.
    prices: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    bundle_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
