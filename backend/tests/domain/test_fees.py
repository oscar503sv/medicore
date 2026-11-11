"""Fees in the domain: amounts, the listed-vs-charged rule, doctors' schedules, and which
procedures may be included in the consultation fee."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from medicore.domain.entities.fee_schedule import FeeSchedule
from medicore.domain.entities.procedure import Procedure, ProcedureDraft, ProcedureType
from medicore.domain.enums import AppointmentType, ProcedureSource
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    ConsultationId,
    FeeScheduleId,
    PatientId,
    ProcedureId,
    ProcedureTypeId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.fee import ZERO, Charge, fee

NOW = datetime(2026, 6, 1, 15, 0, tzinfo=UTC)
TENANT = TenantId.new()


@pytest.mark.parametrize("amount", ["25", "25.5", "25.50", 0, "10000"])
def test_valid_fees(amount):
    assert fee(amount).amount == Decimal(str(amount)).quantize(Decimal("0.01"))


@pytest.mark.parametrize("amount", ["-1", "10000.01", "25.555", "NaN"])
def test_invalid_fees(amount):
    with pytest.raises(InvalidValueObject) as e:
        fee(amount)
    assert e.value.code == "fee.invalid_amount"


def test_a_charge_follows_the_listed_price_until_adjusted():
    charge = Charge.at_list_price(fee(25))
    assert charge.charged == fee(25) and not charge.adjusted
    with pytest.raises(InvalidValueObject) as e:
        charge.adjust(fee(20), None)
    assert e.value.code == "fee.note_required"
    discounted = charge.adjust(fee(20), "  Adulto mayor ")
    assert (discounted.charged, discounted.note, discounted.adjusted) == (
        fee(20), "Adulto mayor", True)
    assert charge.adjust(fee(25), None).note is None  # back to the list price: no reason
    assert Charge().adjust(fee(30), None).charged == fee(30)  # no list price: no reason


def test_a_schedule_prices_every_type_but_procedures():
    schedule = FeeSchedule(id=FeeScheduleId.new(), tenant_id=TENANT, doctor_id=UserId.new())
    schedule.set_prices({AppointmentType.CONSULT: fee(30)}, NOW)
    assert schedule.price_for(AppointmentType.CONSULT) == fee(30)
    assert schedule.price_for(AppointmentType.FOLLOW_UP) is None
    with pytest.raises(InvalidValueObject) as e:
        schedule.set_prices({AppointmentType.PROCEDURE: fee(50)}, NOW)
    assert e.value.code == "fee.procedure_from_catalog"


def _kind(price="40") -> ProcedureType:
    return ProcedureType(id=ProcedureTypeId.new(), tenant_id=TENANT, name="Sutura",
                         price=fee(price))


def _procedure(kind: ProcedureType, consultation: bool) -> Procedure:
    if consultation:
        return Procedure.from_draft(
            ProcedureDraft.of(kind, "Herida"), tenant_id=TENANT, patient_id=PatientId.new(),
            ordered_by_id=UserId.new(), consultation_id=ConsultationId.new(), now=NOW,
        )
    return Procedure(
        id=ProcedureId.new(), tenant_id=TENANT, patient_id=PatientId.new(), type_id=kind.id,
        type_name=kind.name, performer=kind.performer, requires_consent=False,
        source=ProcedureSource.DIRECT, indication="Herida", ordered_by_id=UserId.new(),
        created_by_id=UserId.new(), charge=Charge.at_list_price(kind.price),
    )


def test_an_indicated_procedure_carries_the_catalog_price_or_is_included():
    kind = _kind()
    charged = Procedure.from_draft(
        ProcedureDraft.of(kind, "Herida"), tenant_id=TENANT, patient_id=PatientId.new(),
        ordered_by_id=UserId.new(), consultation_id=ConsultationId.new(), now=NOW,
    )
    assert (charged.charge.listed, charged.charge.charged, charged.fee_included) == (
        fee(40), fee(40), False)
    included = Procedure.from_draft(
        ProcedureDraft.of(kind, "Herida", included=True), tenant_id=TENANT,
        patient_id=PatientId.new(), ordered_by_id=UserId.new(),
        consultation_id=ConsultationId.new(), now=NOW,
    )
    assert (included.charge.listed, included.charge.charged, included.fee_included) == (
        fee(40), ZERO, True)


def test_only_a_procedure_from_a_consultation_can_be_included():
    walk_in = _procedure(_kind(), consultation=False)
    with pytest.raises(DomainError) as e:
        walk_in.set_fee(included=True, charged=None, note=None)
    assert e.value.code == "fee.included_needs_consultation"

    ordered = _procedure(_kind(), consultation=True)
    ordered.set_fee(included=True, charged=None, note=None)
    assert (ordered.charge.charged, ordered.fee_included) == (ZERO, True)
    ordered.set_fee(included=False, charged=fee(40), note=None)  # charged separately again
    assert (ordered.charge.charged, ordered.fee_included) == (fee(40), False)


def test_a_cancelled_procedure_is_not_charged():
    p = _procedure(_kind(), consultation=False)
    p.cancel(UserId.new(), "Paciente no llegó", NOW)
    with pytest.raises(DomainError):
        p.set_fee(included=False, charged=fee(10), note="x")
