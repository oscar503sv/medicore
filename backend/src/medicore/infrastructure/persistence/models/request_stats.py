"""ORM model for hourly request metrics per route (global; 30-day retention)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class RequestStatsModel(Base):
    __tablename__ = "request_stats"

    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    method: Mapped[str] = mapped_column(String(10), primary_key=True)
    route: Mapped[str] = mapped_column(String(300), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    client_errors: Mapped[int] = mapped_column(Integer, nullable=False)
    server_errors: Mapped[int] = mapped_column(Integer, nullable=False)
    total_ms: Mapped[float] = mapped_column(Float, nullable=False)
    max_ms: Mapped[float] = mapped_column(Float, nullable=False)
    # LatencyHistogram bucket counts (domain.value_objects.latency_histogram.BOUNDS_MS).
    buckets: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
