"""Tests for the Prescription lifecycle (active → completed | cancelled) and expiry."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from medicore.domain.entities.prescription import Prescription
from medicore.domain.enums import PrescriptionStatus
from medicore.domain.shared.errors import (
    InvalidStateTransition,
    InvalidValueObject,
    PermissionDenied,
)
from medicore.domain.shared.identifiers import (
    PatientId,
    PrescriptionId,
    TenantId,
    UserId,
)


def make_prescription(end_date: date | None = None) -> Prescription:
    return Prescription(
        id=PrescriptionId.new(),
        tenant_id=TenantId.new(),
        patient_id=PatientId.new(),
        prescriber_id=UserId.new(),
        drug="Enalapril",
        dose="20 mg",
        schedule="1× día",
        start_date=date(2026, 6, 1),
        end_date=end_date,
    )


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
REASON = "Allergic reaction reported"


class TestPrescriptionTransitions:
    def test_complete_active_records_who_and_when(self):
        rx = make_prescription()
        rx.complete(rx.prescriber_id, NOW)
        assert rx.status == PrescriptionStatus.COMPLETED
        assert rx.closed_at == NOW
        assert rx.closed_by_id == rx.prescriber_id
        assert rx.cancel_reason is None

    def test_cancel_active_keeps_the_stripped_reason(self):
        rx = make_prescription()
        rx.cancel(rx.prescriber_id, f"  {REASON}  ", NOW)
        assert rx.status == PrescriptionStatus.CANCELLED
        assert rx.cancel_reason == REASON
        assert rx.closed_at == NOW
        assert rx.closed_by_id == rx.prescriber_id

    @pytest.mark.parametrize("reason", ["", "   ", "x" * 9, "  " + "x" * 9 + "  ", "x" * 501])
    def test_cancel_reason_out_of_range_rejected(self, reason):
        rx = make_prescription()
        with pytest.raises(InvalidValueObject) as exc:
            rx.cancel(rx.prescriber_id, reason, NOW)
        assert exc.value.code == "prescription.cancel_reason_invalid"
        assert exc.value.params == {"min": 10, "max": 500}
        assert rx.status == PrescriptionStatus.ACTIVE
        assert rx.closed_at is None

    @pytest.mark.parametrize("length", [10, 500])
    def test_cancel_reason_bounds_accepted(self, length):
        rx = make_prescription()
        rx.cancel(rx.prescriber_id, "x" * length, NOW)
        assert rx.status == PrescriptionStatus.CANCELLED

    def test_other_user_cannot_complete_or_cancel(self):
        rx = make_prescription()
        other = UserId.new()
        with pytest.raises(PermissionDenied) as complete_exc:
            rx.complete(other, NOW)
        with pytest.raises(PermissionDenied) as cancel_exc:
            rx.cancel(other, REASON, NOW)
        assert complete_exc.value.code == cancel_exc.value.code == "prescription.not_own"
        assert rx.status == PrescriptionStatus.ACTIVE

    def test_authorship_is_checked_before_the_state(self):
        rx = make_prescription()
        rx.complete(rx.prescriber_id, NOW)
        with pytest.raises(PermissionDenied):
            rx.cancel(UserId.new(), REASON, NOW)

    def test_complete_cancelled_rejected(self):
        rx = make_prescription()
        rx.cancel(rx.prescriber_id, REASON, NOW)
        with pytest.raises(InvalidStateTransition):
            rx.complete(rx.prescriber_id, NOW)

    def test_cancel_completed_rejected(self):
        rx = make_prescription()
        rx.complete(rx.prescriber_id, NOW)
        with pytest.raises(InvalidStateTransition):
            rx.cancel(rx.prescriber_id, REASON, NOW)

    def test_complete_twice_rejected(self):
        rx = make_prescription()
        rx.complete(rx.prescriber_id, NOW)
        with pytest.raises(InvalidStateTransition):
            rx.complete(rx.prescriber_id, NOW)


class TestPrescriptionExpiry:
    def test_active_past_end_date_is_expired(self):
        rx = make_prescription(end_date=date(2026, 6, 30))
        assert rx.is_expired_on(date(2026, 7, 1))

    def test_active_before_end_date_is_not_expired(self):
        rx = make_prescription(end_date=date(2026, 6, 30))
        assert not rx.is_expired_on(date(2026, 6, 30))  # last day still counts

    def test_indefinite_prescription_never_expires(self):
        rx = make_prescription(end_date=None)
        assert not rx.is_expired_on(date(2030, 1, 1))

    def test_completed_is_not_expired(self):
        rx = make_prescription(end_date=date(2026, 6, 30))
        rx.complete(rx.prescriber_id, NOW)
        assert not rx.is_expired_on(date(2026, 7, 1))
