"""TenantCounter model — per-tenant sequential display code counters.

Uses SELECT ... FOR UPDATE to safely increment counters under concurrent load.
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class TenantCounterModel(Base):
    __tablename__ = "tenant_counters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "series", name="uq_counters_tenant_series"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    series: Mapped[str] = mapped_column(String(30), nullable=False)
    last_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
