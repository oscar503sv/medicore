"""BookingRules JSONB mapping: legacy keys are ignored, only current keys are written."""

from __future__ import annotations

import uuid

from medicore.domain.entities.availability import BookingRules, DoctorAvailability
from medicore.domain.shared.identifiers import AvailabilityId, TenantId, UserId
from medicore.infrastructure.persistence.mappers.availability import (
    from_doctor_availability,
    to_doctor_availability,
)
from medicore.infrastructure.persistence.models.availability import DoctorAvailabilityModel


def _row(rules: dict) -> DoctorAvailabilityModel:
    return DoctorAvailabilityModel(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), doctor_id=uuid.uuid4(), weekly=[], rules=rules
    )


def test_legacy_rule_keys_in_stored_json_are_ignored():
    row = _row(
        {
            "slot_minutes": 20,
            "buffer_minutes": 15,  # legacy — removed from BookingRules
            "min_advance_hours": 2,
            "max_advance_days": 90,  # legacy — removed from BookingRules
            "allow_same_day": False,
        }
    )
    availability = to_doctor_availability(row, exceptions=[])
    assert availability.rules == BookingRules(
        slot_minutes=20, min_advance_hours=2, allow_same_day=False
    )


def test_rules_serialize_exactly_three_keys():
    availability = DoctorAvailability(
        id=AvailabilityId.new(),
        tenant_id=TenantId.new(),
        doctor_id=UserId.new(),
        rules=BookingRules(slot_minutes=45, min_advance_hours=4, allow_same_day=False),
    )
    av_dict, _ = from_doctor_availability(availability)
    assert av_dict["rules"] == {
        "slot_minutes": 45,
        "min_advance_hours": 4,
        "allow_same_day": False,
    }
