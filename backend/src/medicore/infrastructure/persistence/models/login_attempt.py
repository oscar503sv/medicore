"""ORM model for the global failed-login throttle (not tenant-scoped)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class LoginAttemptModel(Base):
    __tablename__ = "login_attempts"

    # "tenant:{slug}:{email}" or "platform:{email}", lowercased.
    identifier: Mapped[str] = mapped_column(String(600), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
