"""Tenant-timezone helpers shared across use cases.

Slots and appointments are stored/compared as naive wall-clock in the clinic's timezone
(see ``slot_resolver._naive``). ``SystemClock`` returns tz-aware UTC, so comparing it directly
against those naive wall-clock datetimes is wrong across timezones (a clinic east/west of UTC
would see "now" shifted by its offset). These helpers reconcile the two references.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.shared.identifiers import TenantId


def to_naive(dt: datetime) -> datetime:
    """Drop tzinfo so naive (wall-clock) and aware (clock/DB ``timestamptz``) datetimes compare."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def clinic_now(uow: UnitOfWork, tenant_id: TenantId, clock: Clock) -> datetime:
    """Current instant as the clinic's local wall-clock (naive).

    ``SystemClock`` returns tz-aware UTC, so we convert it to the tenant's timezone and drop
    tzinfo. A naive clock (tests' ``FixedClock``) is already wall-clock and passes through.
    """
    now = clock.now()
    if now.tzinfo is None:
        return now
    tenant = uow.tenants.get_by_id(tenant_id)
    tz = ZoneInfo(tenant.timezone) if tenant and tenant.timezone else UTC
    return now.astimezone(tz).replace(tzinfo=None)
