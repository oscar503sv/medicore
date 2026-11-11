"""Tenant aggregate (organization / clinic) and its Location entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from medicore.domain.enums import IcdVersion, PracticeModel, TenantStatus
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import LocationId, TenantId
from medicore.domain.value_objects.print_settings import PrintSettings
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.subscription import Subscription


@dataclass(slots=True)
class Location:
    """A clinic site within a tenant."""

    id: LocationId
    tenant_id: TenantId
    name: str  # e.g. "San Salvador · Escalón"
    address: str | None = None
    phone: str | None = None  # printed on the clinic's documents
    is_primary: bool = False


@dataclass(slots=True)
class Tenant:
    """Root of the multi-tenant model. The tenant itself carries no ``tenant_id``."""

    id: TenantId
    legal_name: str
    tax_id: str
    slug: Slug
    timezone: str  # IANA, e.g. "America/El_Salvador"
    # Plan, modules and paid period; set only from the platform console.
    subscription: Subscription
    status: TenantStatus = TenantStatus.ACTIVE
    icd_version: IcdVersion = IcdVersion.CIE11
    locations: list[Location] = field(default_factory=list)
    # Decides the default permissions on fees and income (see PracticeModel).
    practice_model: PracticeModel = PracticeModel.ASSOCIATED
    print_settings: PrintSettings = field(default_factory=PrintSettings)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.locations:
            raise InvalidValueObject("Tenant must have at least one Location")
        self._ensure_single_primary()

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE

    def suspend(self) -> None:
        self.status = TenantStatus.SUSPENDED

    def activate(self) -> None:
        self.status = TenantStatus.ACTIVE

    def archive(self) -> None:
        self.status = TenantStatus.ARCHIVED

    @property
    def primary_location(self) -> Location:
        for loc in self.locations:
            if loc.is_primary:
                return loc
        return self.locations[0]

    def add_location(self, location: Location) -> None:
        if location.tenant_id != self.id:
            raise DomainError("Location belongs to a different tenant")
        self.locations.append(location)
        self._ensure_single_primary()

    def _ensure_single_primary(self) -> None:
        primaries = [loc for loc in self.locations if loc.is_primary]
        if len(primaries) > 1:
            raise InvalidValueObject("Tenant cannot have more than one primary Location")
        # If none is primary, promote the first so there is always a default.
        if not primaries:
            self.locations[0].is_primary = True
