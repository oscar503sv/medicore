"""Regression tests for SqlAppointmentRepository overlap detection.

SQLite (used in local dev) returns naive datetimes for ``DateTime(timezone=True)``
columns, while request datetimes arrive tz-aware. ``find_overlapping`` must compare
them on a single wall-clock reference instead of crashing with
``TypeError: can't compare offset-naive and offset-aware datetimes``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from medicore.domain.shared.identifiers import TenantId, UserId
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.repositories.appointment import (
    SqlAppointmentRepository,
)


class _FakeQuery:
    """Stands in for a SQLAlchemy query; ignores filters and returns canned rows."""

    def __init__(self, rows: list[AppointmentModel]) -> None:
        self._rows = rows

    def filter(self, *args: object, **kwargs: object) -> _FakeQuery:
        return self

    def order_by(self, *args: object) -> _FakeQuery:
        return self

    def all(self) -> list[AppointmentModel]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[AppointmentModel]) -> None:
        self._rows = rows

    def query(self, *args: object) -> _FakeQuery:
        return _FakeQuery(self._rows)


def _naive_row(doctor_id: UserId, tenant_id: TenantId) -> AppointmentModel:
    """A persisted appointment as SQLite hands it back: naive scheduled_start."""
    return AppointmentModel(
        id=uuid4(),
        tenant_id=tenant_id.value,
        code="A-0001",
        patient_id=uuid4(),
        doctor_id=doctor_id.value,
        location_id=uuid4(),
        type="consult",
        status="scheduled",
        scheduled_start=datetime(2026, 6, 1, 9, 0),  # naive, 09:00-09:30
        duration_minutes=30,
        reason="Control",
        room=None,
        created_by_id=uuid4(),
        created_at=datetime(2026, 6, 1, 8, 0),
        updated_at=datetime(2026, 6, 1, 8, 0),
    )


def test_find_overlapping_compares_naive_store_against_aware_request():
    doctor = UserId.new()
    tenant = TenantId.new()
    repo = SqlAppointmentRepository(_FakeSession([_naive_row(doctor, tenant)]), tenant)

    # Aware request that overlaps the naive 09:00-09:30 stored appointment.
    start = datetime(2026, 6, 1, 9, 15, tzinfo=UTC)
    end = datetime(2026, 6, 1, 9, 45, tzinfo=UTC)

    overlapping = repo.find_overlapping(doctor, start, end)

    assert len(overlapping) == 1


def test_find_overlapping_excludes_non_overlapping_aware_request():
    doctor = UserId.new()
    tenant = TenantId.new()
    repo = SqlAppointmentRepository(_FakeSession([_naive_row(doctor, tenant)]), tenant)

    # Aware request starting exactly when the stored 09:00-09:30 slot ends.
    start = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
    end = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)

    assert repo.find_overlapping(doctor, start, end) == []
