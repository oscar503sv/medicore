"""Pricing of vaccine doses: private doses are charged, MINSAL ones are free by law."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.entities.vaccine_price import VaccinePrice
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    VaccinationOutcome,
    VaccinationSource,
    VaccineSupply,
)
from medicore.domain.services.vaccine_fees import VaccinePriceMissing, dose_fee, doses_total
from medicore.domain.shared.errors import DomainError, InvalidValueObject
from medicore.domain.shared.identifiers import (
    AppointmentId,
    LocationId,
    PatientId,
    ServiceAgendaId,
    TenantId,
    UserId,
    VaccinationRecordId,
)
from medicore.domain.value_objects.fee import ZERO, Charge, fee

TENANT = TenantId.new()
APPT = AppointmentId.new()
NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


def _dose(**kw) -> VaccinationRecord:
    base = dict(
        id=VaccinationRecordId.new(), tenant_id=TENANT, patient_id=PatientId.new(),
        vaccine_code="TD", dose_key=None, outcome=VaccinationOutcome.ADMINISTERED,
        occurred_on=date(2026, 6, 1), source=VaccinationSource.CLINIC,
        recorded_by_id=UserId.new(), appointment_id=APPT, lot="L-1",
        supply=VaccineSupply.CLINIC, listed_fee=fee("25"),
    )
    base.update(kw)
    return VaccinationRecord(**base)


def _visit(charge: Charge | None = None, status=AppointmentStatus.IN_PROGRESS) -> Appointment:
    return Appointment(
        id=APPT, tenant_id=TENANT, code="A-1", patient_id=PatientId.new(), doctor_id=None,
        agenda_id=ServiceAgendaId.new(), location_id=LocationId.new(),
        type=AppointmentType.VACCINATION, scheduled_start=datetime(2026, 6, 1, 9),
        duration_minutes=15, reason="Vacunas", created_by_id=UserId.new(), status=status,
        charge=charge or Charge(),
    )


class TestDoseFee:
    def test_a_minsal_dose_is_free_even_when_the_clinic_has_a_price(self):
        assert dose_fee("TD", VaccineSupply.MINSAL, fee("25")) == ZERO

    def test_a_minsal_dose_needs_no_price(self):
        assert dose_fee("TD", VaccineSupply.MINSAL, None) == ZERO

    def test_a_private_dose_is_charged_at_the_clinic_price(self):
        assert dose_fee("TD", VaccineSupply.CLINIC, fee("25")) == fee("25")

    def test_a_private_dose_may_be_priced_at_zero(self):
        assert dose_fee("TD", VaccineSupply.CLINIC, fee("0")) == ZERO

    def test_a_private_dose_without_a_price_is_refused(self):
        with pytest.raises(VaccinePriceMissing) as error:
            dose_fee("TD", VaccineSupply.CLINIC, None)

        assert error.value.code == "vaccination.price_missing"
        assert error.value.params == {"vaccine": "TD"}


class TestDosesTotal:
    def test_adds_the_copied_prices(self):
        assert doses_total([_dose(), _dose(listed_fee=fee("10.50"))]) == fee("35.50")

    def test_skips_voided_doses_and_unpriced_ones(self):
        voided = _dose()
        voided.void(UserId.new(), "error", NOW)
        # Given elsewhere: nothing to charge.
        legacy = _dose(supply=None, listed_fee=None, source=VaccinationSource.EXTERNAL, lot=None)

        assert doses_total([voided, legacy, _dose(listed_fee=fee("5"))]) == fee("5")

    def test_nothing_adds_up_to_zero(self):
        assert doses_total([]) == ZERO


class TestVaccinationRecordSupply:
    def test_a_dose_given_here_needs_its_supplier(self):
        with pytest.raises(InvalidValueObject) as error:
            _dose(supply=None, listed_fee=None)

        assert error.value.code == "vaccination.supply_required"

    @pytest.mark.parametrize(
        "kw",
        [
            {"source": VaccinationSource.EXTERNAL, "lot": None},
            {"outcome": VaccinationOutcome.REFUSED, "lot": None},
        ],
    )
    def test_a_dose_not_given_here_has_no_supplier(self, kw):
        with pytest.raises(InvalidValueObject) as error:
            _dose(listed_fee=None, **kw)

        assert error.value.code == "vaccination.supply_not_applicable"

    def test_a_minsal_dose_cannot_carry_a_price(self):
        with pytest.raises(InvalidValueObject) as error:
            _dose(supply=VaccineSupply.MINSAL, listed_fee=fee("1"))

        assert error.value.code == "vaccination.minsal_free"

    def test_a_minsal_dose_may_carry_zero(self):
        assert _dose(supply=VaccineSupply.MINSAL, listed_fee=ZERO).listed_fee == ZERO

    def test_a_price_needs_an_appointment(self):
        with pytest.raises(InvalidValueObject) as error:
            _dose(appointment_id=None)

        assert error.value.code == "vaccination.fee_needs_visit"

    def test_a_dose_outside_an_appointment_may_have_a_supplier_and_no_price(self):
        record = _dose(appointment_id=None, listed_fee=None)

        assert record.supply == VaccineSupply.CLINIC


class TestVaccinePrice:
    def test_knows_only_catalog_vaccines(self):
        with pytest.raises(InvalidValueObject) as error:
            VaccinePrice(TENANT, "NOPE", fee("5"), NOW)

        assert error.value.code == "vaccine_price.unknown_vaccine"

    def test_the_price_is_a_valid_fee(self):
        from medicore.domain.value_objects.money import Money

        with pytest.raises(InvalidValueObject):
            VaccinePrice(TENANT, "TD", Money(Decimal("-1"), "USD"), NOW)


class TestPriceFromDoses:
    def test_an_unpriced_visit_takes_the_total(self):
        visit = _visit()

        visit.price_from_doses(fee("45"))

        assert visit.charge == Charge.at_list_price(fee("45"))

    def test_an_untouched_charge_follows_the_total(self):
        visit = _visit(Charge.at_list_price(fee("20")))

        visit.price_from_doses(fee("45"))

        assert visit.charge.charged == fee("45")

    def test_a_discount_stays_and_keeps_its_note(self):
        visit = _visit(Charge(listed=fee("45"), charged=fee("30"), note="Cortesía"))

        visit.price_from_doses(fee("60"))

        assert visit.charge == Charge(listed=fee("60"), charged=fee("30"), note="Cortesía")

    def test_a_discount_is_capped_at_the_new_total(self):
        visit = _visit(Charge(listed=fee("45"), charged=fee("30"), note="Cortesía"))

        visit.price_from_doses(fee("20"))

        assert visit.charge == Charge.at_list_price(fee("20"))  # nothing left to explain


class TestAdjustVaccinationFee:
    def test_cannot_adjust_before_any_dose_is_recorded(self):
        with pytest.raises(DomainError) as error:
            _visit().adjust_fee(fee("0"), None)

        assert error.value.code == "fee.vaccination_pending"

    def test_cannot_raise_above_the_doses(self):
        visit = _visit(Charge.at_list_price(fee("45")))

        with pytest.raises(DomainError) as error:
            visit.adjust_fee(fee("50"), "x")

        assert error.value.code == "fee.vaccination_above_list"
        assert error.value.params == {"max": "45.00"}

    def test_a_discount_is_allowed(self):
        visit = _visit(Charge.at_list_price(fee("45")))

        visit.adjust_fee(fee("40"), "Cortesía")

        assert visit.charge.charged == fee("40")

    @pytest.mark.parametrize(
        "status", [AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW]
    )
    def test_a_closed_visit_without_priced_doses_has_no_fee(self, status):
        with pytest.raises(DomainError) as error:
            _visit(status=status).adjust_fee(fee("10"), None)

        assert error.value.code == "fee.vaccination_unpriced"
