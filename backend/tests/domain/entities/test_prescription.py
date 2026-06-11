"""Tests for the Prescription lifecycle (active → completed | cancelled) and expiry."""

from __future__ import annotations

from datetime import date

import pytest

from medicore.domain.entities.prescription import Prescription
from medicore.domain.enums import PrescriptionStatus
from medicore.domain.shared.errors import InvalidStateTransition
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


class TestPrescriptionTransitions:
    def test_complete_active(self):
        rx = make_prescription()
        rx.complete()
        assert rx.status == PrescriptionStatus.COMPLETED

    def test_cancel_active(self):
        rx = make_prescription()
        rx.cancel()
        assert rx.status == PrescriptionStatus.CANCELLED

    def test_complete_cancelled_rejected(self):
        rx = make_prescription()
        rx.cancel()
        with pytest.raises(InvalidStateTransition):
            rx.complete()

    def test_cancel_completed_rejected(self):
        rx = make_prescription()
        rx.complete()
        with pytest.raises(InvalidStateTransition):
            rx.cancel()

    def test_complete_twice_rejected(self):
        rx = make_prescription()
        rx.complete()
        with pytest.raises(InvalidStateTransition):
            rx.complete()


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
        rx.complete()
        assert not rx.is_expired_on(date(2026, 7, 1))
