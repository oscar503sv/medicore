"""ORM models for Tenant and Location."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from medicore.infrastructure.database.base import Base


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_id: Mapped[str] = mapped_column(String(50), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, default="America/El_Salvador"
    )
    # Subscription (see domain.value_objects.subscription).
    plan_code: Mapped[str] = mapped_column(
        String(30), ForeignKey("plans.code", onupdate="CASCADE"), nullable=False
    )
    modules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    # Per-clinic overrides; NULL = use the plan's.
    limit_doctors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_support_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_locations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_storage_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active", default="active"
    )
    icd_version: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="cie11", default="cie11"
    )
    practice_model: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="associated", default="associated"
    )
    print_paper: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="half_letter", default="half_letter"
    )
    print_letterhead: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    note_settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    locations: Mapped[list[LocationModel]] = relationship(
        "LocationModel", back_populates="tenant", cascade="all, delete-orphan"
    )


class LocationModel(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    tenant: Mapped[TenantModel] = relationship("TenantModel", back_populates="locations")
