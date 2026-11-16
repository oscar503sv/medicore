"""ORM model for a service agenda (the vaccination room, ...)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from medicore.infrastructure.database.base import Base


class ServiceAgendaModel(Base):
    __tablename__ = "service_agendas"
    __table_args__ = (
        # One name per clinic, however it is capitalized.
        Index("uq_service_agendas_tenant_name", "tenant_id", text("lower(name)"), unique=True),
        # Lets appointments and schedules point at an agenda together with its clinic.
        UniqueConstraint("tenant_id", "id", name="uq_service_agendas_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"],
            name="fk_service_agendas_tenant_location",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
