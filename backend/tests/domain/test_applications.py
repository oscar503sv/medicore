"""Domain rules for in-clinic applications: orders, dose records and the allergy alert."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from medicore.domain.entities.application import (
    ApplicationAlreadyVoided,
    ApplicationOrder,
    ApplicationOrderClosed,
    ApplicationRecord,
    ObservationNotOpen,
)
from medicore.domain.enums import (
    ApplicationOrderSource,
    ApplicationOrderStatus,
    ApplicationOutcome,
    ApplicationRoute,
)
from medicore.domain.services.allergies import allergy_conflicts
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    PatientId,
    TenantId,
    UserId,
)

START = datetime(2026, 5, 31, 9, 0)
NOW = datetime(2026, 5, 31, 9, 10)


def order(**kw) -> ApplicationOrder:
    defaults = dict(
        id=ApplicationOrderId.new(), tenant_id=TenantId.new(), patient_id=PatientId.new(),
        drug="Ceftriaxona", dose="1 g", route=ApplicationRoute.INTRAMUSCULAR,
        source=ApplicationOrderSource.INTERNAL, starts_at=START, created_by_id=UserId.new(),
        ordered_by_id=UserId.new(), doses_total=3, interval_hours=24,
    )
    defaults.update(kw)
    return ApplicationOrder(**defaults)


def record(**kw) -> ApplicationRecord:
    defaults = dict(
        id=ApplicationRecordId.new(), tenant_id=TenantId.new(),
        order_id=ApplicationOrderId.new(), patient_id=PatientId.new(), dose_number=1,
        outcome=ApplicationOutcome.APPLIED, recorded_at=NOW, recorded_by_id=UserId.new(),
        observe_until=NOW + timedelta(minutes=30),
    )
    defaults.update(kw)
    return ApplicationRecord(**defaults)


def test_dose_schedule_and_status_follow_the_settled_doses():
    o = order()
    assert [o.due_at(n) for n in (1, 2, 3)] == [START, START + timedelta(days=1),
                                                START + timedelta(days=2)]
    assert o.next_dose(set()) == 1 and o.next_dose({1, 3}) == 2
    o.refresh({1})
    assert o.status == ApplicationOrderStatus.IN_PROGRESS
    o.refresh({1, 2, 3})
    assert o.status == ApplicationOrderStatus.COMPLETED and not o.is_open
    o.refresh({1, 2})  # a dose voided → back in progress
    assert o.status == ApplicationOrderStatus.IN_PROGRESS


def test_single_dose_drops_the_interval_and_several_need_one():
    assert order(doses_total=1, interval_hours=8).interval_hours is None
    with pytest.raises(InvalidValueObject) as exc:
        order(doses_total=2, interval_hours=None)
    assert exc.value.code == "application.interval_required"
    with pytest.raises(InvalidValueObject) as exc:
        order(observation_minutes=300)
    assert exc.value.code == "application.invalid_observation"


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"external_prescriber": None, "external_jvpm": "12345"},
         "application.prescriber_required"),
        ({"external_prescriber": "Dr. Ramos", "external_jvpm": "ABC"},
         "application.invalid_jvpm"),
    ],
)
def test_external_orders_name_the_prescriber_and_jvpm(kw, code):
    with pytest.raises(InvalidValueObject) as exc:
        order(source=ApplicationOrderSource.EXTERNAL, ordered_by_id=None, **kw)
    assert exc.value.code == code
    ok = order(source=ApplicationOrderSource.EXTERNAL, ordered_by_id=None,
               external_prescriber=" Dr. Ramos ", external_jvpm="12345")
    assert ok.external_prescriber == "Dr. Ramos"


def test_cancel_needs_a_reason_and_an_open_order():
    o = order()
    with pytest.raises(InvalidValueObject):
        o.cancel(UserId.new(), "  ", NOW)
    o.cancel(UserId.new(), "Paciente trasladado", NOW)
    assert o.status == ApplicationOrderStatus.CANCELLED
    o.refresh({1, 2, 3})
    assert o.status == ApplicationOrderStatus.CANCELLED  # cancelled stays cancelled
    with pytest.raises(ApplicationOrderClosed):
        o.cancel(UserId.new(), "otra vez", NOW)


def test_observation_closes_once_and_a_reaction_needs_a_description():
    r = record()
    assert r.observing
    with pytest.raises(InvalidValueObject) as exc:
        r.close_observation(UserId.new(), True, "", NOW)
    assert exc.value.code == "application.reaction_notes_required"
    r.close_observation(UserId.new(), True, "Urticaria leve en brazo", NOW)
    assert not r.observing and r.reaction
    with pytest.raises(ObservationNotOpen):
        r.close_observation(UserId.new(), False, None, NOW)


def test_a_dose_not_applied_has_no_lot_nor_observation_and_voids_once():
    r = record(outcome=ApplicationOutcome.REFUSED, lot="L1")
    assert r.lot is None and r.observe_until is None and not r.observing
    r.void(UserId.new(), "Registrado por error", NOW)
    with pytest.raises(ApplicationAlreadyVoided):
        r.void(UserId.new(), "otra vez", NOW)


def test_vitals_on_the_record_are_validated():
    with pytest.raises(InvalidValueObject):
        record(blood_pressure="alta")
    with pytest.raises(InvalidValueObject):
        record(temperature=50)


@pytest.mark.parametrize(
    ("drug", "allergies", "hits"),
    [
        ("Penicilina benzatínica 1.2 M", ["Penicilina"], ["Penicilina"]),
        ("Amoxicilina", ["penicilinas"], ["penicilinas"]),
        ("Ketorolaco 30 mg", ["AINE", "Látex"], ["AINE"]),
        ("Diclofenaco", ["Diclofenaco sódico"], ["Diclofenaco sódico"]),
        ("Metamizol", ["Dipirona"], ["Dipirona"]),
        ("Dexametasona", ["Penicilina", "AINE"], []),
        ("Ceftriaxona", ["Polen"], []),
    ],
)
def test_allergy_alert(drug, allergies, hits):
    assert allergy_conflicts(drug, allergies) == hits
