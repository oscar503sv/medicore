"""ORM model for a clinic's price per vaccine (no row means no price)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class VaccinePriceModel(Base):
    __tablename__ = "vaccine_prices"
    __table_args__ = (
        CheckConstraint("price >= 0 AND price <= 10000", name="ck_vaccine_prices_range"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    # The vaccine catalog lives in code, so there is no foreign key to it.
    vaccine_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
