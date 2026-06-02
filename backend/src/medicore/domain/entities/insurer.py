"""Insurer aggregate — a tenant-managed catalog of health insurers/payers.

Patients reference an insurer instead of carrying a free-text name, so the same payer can be
administered in one place (contact details, address) and reused across patients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.shared.identifiers import InsurerId, TenantId


@dataclass(slots=True)
class Insurer:
    """A health insurer / payer the clinic works with."""

    id: InsurerId
    tenant_id: TenantId
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    contact_person: str | None = None
    notes: str | None = None
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def archive(self) -> None:
        self.active = False
        self._touch()

    def reactivate(self) -> None:
        self.active = True
        self._touch()

    def _touch(self) -> None:
        self.updated_at = datetime.now(UTC)
