"""ORM model for the global failed-login throttle (not tenant-scoped)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class LoginAttemptModel(Base):
    __tablename__ = "login_attempts"

    # An IP ("ip:{key}"), an account and IP ("{account}|{key}") or an account
    # ("tenant:{slug}:{email}", "platform:{email}", "platform-mfa:{admin_id}"), lowercased.
    # See application.common.login_throttle.
    identifier: Mapped[str] = mapped_column(String(600), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Last successful sign-in for an account and IP: that IP is exempt from the account's cap.
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
