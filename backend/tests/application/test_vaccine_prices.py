"""Vaccine prices and the charge of a vaccination visit (private doses add up, MINSAL is free)."""

from __future__ import annotations

from datetime import date

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.fees import AdjustAppointmentFee
from medicore.application.use_cases.vaccinations import (
    RecordVaccination,
    RecordVaccinationCommand,
    VisitDose,
    VoidVaccination,
)
from medicore.application.use_cases.vaccine_prices import ListVaccinePrices, SetVaccinePrice
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.tenant import Subscription
from medicore.domain.enums import (
    AppointmentStatus,
    Role,
    VaccinationOutcome,
    VaccinationSource,
    VaccineSupply,
)
from medicore.domain.shared.errors import DomainError, InvalidValueObject, PermissionDenied
from medicore.domain.shared.identifiers import ConsultationId
from medicore.domain.value_objects.fee import fee
from tests.application.test_vaccination_visit import (
    MONDAY_9AM,
    _agenda,
    _appointment,
    _uow,
    _visit,
)
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock

PRIVATE = VaccineSupply.CLINIC
MINSAL = VaccineSupply.MINSAL


def _set(seed, code, price, actor=None):
    return SetVaccinePrice(_uow(seed), FixedClock()).execute(
        actor or seed.actor(seed.admin), code, None if price is None else fee(price)
    )


def _dose(vaccine="TD", supply=PRIVATE, lot="L-1", **kw):
    return VisitDose(vaccine_code=vaccine, lot=lot, supply=supply, **kw)


@pytest.fixture
def clinic():
    seed = seed_clinic()
    return seed, _agenda(seed)


class TestPriceList:
    def test_lists_every_vaccine_in_catalog_order_with_its_price(self, clinic):
        seed, _ = clinic
        _set(seed, "TD", "12.50")

        view = ListVaccinePrices(_uow(seed)).execute(seed.actor(seed.nurse))

        assert view.editable is False
        td = next(i for i in view.items if i.vaccine_code == "TD")
        assert td.price == fee("12.50") and td.updated_at is not None
        assert next(i for i in view.items if i.vaccine_code == "BCG").price is None
        assert view.items[0].vaccine_code == "BCG"

    def test_whoever_manages_every_fee_may_edit(self, clinic):
        seed, _ = clinic

        assert ListVaccinePrices(_uow(seed)).execute(seed.actor(seed.admin)).editable

    def test_it_needs_the_vaccination_module(self, clinic):
        seed, _ = clinic
        seed.tenant.subscription = Subscription(plan_code="clinica", modules=frozenset())

        with pytest.raises(PermissionDenied) as error:
            ListVaccinePrices(_uow(seed)).execute(seed.actor(seed.nurse))

        assert error.value.code == "vaccine_price.module_required"


class TestSetPrice:
    def test_sets_replaces_and_removes_a_price_with_an_audit_trail(self, clinic):
        seed, _ = clinic

        _set(seed, "TD", "10")
        _set(seed, "TD", "12")
        _set(seed, "TD", None)

        assert _uow(seed).vaccine_prices.as_map() == {}
        audits = _uow(seed).audit.query(action="vaccine_price.updated")
        assert len(audits) == 3
        assert {(a.metadata["old"], a.metadata["new"]) for a in audits} == {
            (None, "10.00"), ("10.00", "12.00"), ("12.00", None),
        }

    def test_zero_is_a_valid_price(self, clinic):
        seed, _ = clinic

        _set(seed, "TD", "0")

        assert _uow(seed).vaccine_prices.as_map()["TD"] == fee("0")

    @pytest.mark.parametrize("role", [Role.DOCTOR, Role.NURSE, Role.RECEPTIONIST])
    def test_only_fees_manage_all_may_set_it(self, clinic, role):
        seed, _ = clinic
        actor = seed.doctor_actor if role == Role.DOCTOR else seed.actor(
            seed.nurse if role == Role.NURSE else seed.receptionist
        )

        with pytest.raises(PermissionDenied) as error:
            _set(seed, "TD", "5", actor=actor)

        assert error.value.code == "fee.not_allowed"

    def test_unknown_vaccine_is_refused(self, clinic):
        seed, _ = clinic

        with pytest.raises(ValidationError) as error:
            _set(seed, "NOPE", "5")

        assert error.value.code == "vaccine_price.unknown_vaccine"


class TestVisitCharge:
    def test_a_mixed_visit_charges_the_private_doses_only(self, clinic):
        seed, agenda = clinic
        _set(seed, "TD", "25")
        _set(seed, "INFLU", "20")
        appt = _appointment(seed, agenda)

        visit = _visit(seed, appt, _dose("TD"), _dose("INFLU"), _dose("HEPA", MINSAL))

        assert visit.appointment.charge.listed == fee("45")
        assert visit.appointment.charge.charged == fee("45")
        assert [r.listed_fee for r in visit.records] == [fee("25"), fee("20"), fee("0")]
        assert visit.appointment.status == AppointmentStatus.COMPLETED
        assert _uow(seed).audit.query(action="appointment.fee_repriced")

    def test_a_minsal_only_visit_is_free_and_cannot_be_raised(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        visit = _visit(seed, appt, _dose("TD", MINSAL))

        assert visit.appointment.charge.charged == fee("0")
        with pytest.raises(DomainError) as error:
            AdjustAppointmentFee(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), appt.id, fee("5"), "x"
            )
        assert error.value.code == "fee.vaccination_above_list"

    def test_a_private_dose_without_a_price_records_nothing(self, clinic):
        seed, agenda = clinic
        _set(seed, "TD", "25")
        appt = _appointment(seed, agenda)

        with pytest.raises(DomainError) as error:
            _visit(seed, appt, _dose("TD"), _dose("INFLU"))

        assert error.value.code == "vaccination.price_missing"
        assert error.value.params == {"vaccine": "INFLU"}
        assert _uow(seed).vaccinations.list_by_appointment(appt.id) == []
        stored = _uow(seed).appointments.get_by_id(appt.id)
        assert stored.status == AppointmentStatus.SCHEDULED and stored.charge.listed is None

    def test_the_supplier_is_required_for_a_dose_given_here(self, clinic):
        seed, agenda = clinic
        appt = _appointment(seed, agenda)

        with pytest.raises(InvalidValueObject) as error:
            _visit(seed, appt, _dose("TD", None))

        assert error.value.code == "vaccination.supply_required"

    def test_a_later_price_change_does_not_touch_the_visit(self, clinic):
        seed, agenda = clinic
        _set(seed, "TD", "25")
        appt = _appointment(seed, agenda)
        _visit(seed, appt, _dose("TD"))

        _set(seed, "TD", "99")

        stored = _uow(seed).appointments.get_by_id(appt.id)
        assert stored.charge.charged == fee("25")
        assert _uow(seed).vaccinations.list_by_appointment(appt.id)[0].listed_fee == fee("25")

    def test_a_discount_can_be_given_but_not_a_raise(self, clinic):
        seed, agenda = clinic
        _set(seed, "TD", "25")
        appt = _appointment(seed, agenda)
        _visit(seed, appt, _dose("TD"))
        adjust = AdjustAppointmentFee(_uow(seed), FixedClock())

        adjust.execute(seed.actor(seed.admin), appt.id, fee("20"), "Cortesía")
        with pytest.raises(DomainError) as error:
            adjust.execute(seed.actor(seed.admin), appt.id, fee("26"), "x")

        assert error.value.code == "fee.vaccination_above_list"
        assert _uow(seed).appointments.get_by_id(appt.id).charge.charged == fee("20")

    def test_a_second_visit_on_an_open_consultation_adds_to_the_first(self, clinic):
        seed, _ = clinic
        _set(seed, "TD", "25")
        _set(seed, "INFLU", "20")
        appt = _appointment(seed)  # the doctor's own vaccination slot
        appt.start()
        seed.factory.store.appointments[appt.id.value] = appt
        consultation = Consultation(
            id=ConsultationId.new(), tenant_id=seed.tenant.id, appointment_id=appt.id,
            patient_id=seed.patient.id, doctor_id=seed.doctor.id, started_at=MONDAY_9AM,
        )
        seed.factory.store.consultations[consultation.id.value] = consultation
        doctor = seed.doctor_actor
        _visit(seed, appt, _dose("TD"), actor=doctor)

        visit = _visit(seed, appt, _dose("INFLU"), actor=doctor)

        assert visit.appointment.charge.listed == fee("45")


class TestVoidRecalculates:
    def _visit_of_two(self, seed, agenda):
        _set(seed, "TD", "25")
        _set(seed, "INFLU", "20")
        appt = _appointment(seed, agenda)
        visit = _visit(seed, appt, _dose("TD"), _dose("INFLU"), _dose("HEPA", MINSAL))
        return appt, visit

    def _void(self, seed, record):
        return VoidVaccination(_uow(seed), FixedClock()).execute(
            seed.actor(seed.nurse), record.id, "Error"
        )

    def test_voiding_a_private_dose_lowers_the_charge(self, clinic):
        seed, agenda = clinic
        appt, visit = self._visit_of_two(seed, agenda)

        self._void(seed, visit.records[0])

        charge = _uow(seed).appointments.get_by_id(appt.id).charge
        assert charge.listed == fee("20") and charge.charged == fee("20")
        audit = _uow(seed).audit.query(action="appointment.fee_repriced")
        assert audit[-1].metadata["reason"] == "void"

    def test_a_discount_is_capped_by_the_new_total(self, clinic):
        seed, agenda = clinic
        appt, visit = self._visit_of_two(seed, agenda)
        AdjustAppointmentFee(_uow(seed), FixedClock()).execute(
            seed.actor(seed.admin), appt.id, fee("30"), "Cortesía"
        )

        self._void(seed, visit.records[0])  # total 20: the 30 can no longer stand

        assert _uow(seed).appointments.get_by_id(appt.id).charge.charged == fee("20")

    def test_voiding_a_minsal_dose_changes_nothing(self, clinic):
        seed, agenda = clinic
        appt, visit = self._visit_of_two(seed, agenda)
        before = len(_uow(seed).audit.query(action="appointment.fee_repriced"))

        self._void(seed, visit.records[2])

        assert _uow(seed).appointments.get_by_id(appt.id).charge.charged == fee("45")
        assert len(_uow(seed).audit.query(action="appointment.fee_repriced")) == before

    def test_a_legacy_visit_is_left_alone(self, clinic):
        seed, agenda = clinic
        appt, visit = self._visit_of_two(seed, agenda)
        stored = _uow(seed).appointments.get_by_id(appt.id)
        stored.charge = type(stored.charge)()  # as it was before prices existed
        _uow(seed).appointments.save(stored)

        self._void(seed, visit.records[0])

        assert _uow(seed).appointments.get_by_id(appt.id).charge.listed is None


class TestSingleDose:
    def _record(self, seed, supply):
        return RecordVaccination(_uow(seed), FixedClock()).execute(
            seed.actor(seed.nurse),
            RecordVaccinationCommand(
                patient_id=seed.patient.id, vaccine_code="TD",
                outcome=VaccinationOutcome.ADMINISTERED, occurred_on=date(2026, 5, 31),
                source=VaccinationSource.CLINIC, lot="L-1", supply=supply,
            ),
        )

    def test_a_loose_private_dose_needs_no_price_and_is_not_priced(self, clinic):
        seed, _ = clinic

        record = self._record(seed, PRIVATE)

        assert record.supply == PRIVATE and record.listed_fee is None

    def test_the_supplier_is_required(self, clinic):
        seed, _ = clinic

        with pytest.raises(InvalidValueObject) as error:
            self._record(seed, None)

        assert error.value.code == "vaccination.supply_required"


class TestClosingWithoutADoseVisit:
    """Whatever closes a vaccination appointment, it is charged only its private doses."""

    def _doctors_appointment(self, seed):
        from medicore.application.use_cases.consultations import StartConsultation

        appt = _appointment(seed)
        return appt, StartConsultation(_uow(seed), FixedClock()).execute(
            seed.doctor_actor, appt.id
        )

    def _sign(self, seed, consultation):
        from medicore.application.use_cases.consultations import (
            SignConsultation,
            SignConsultationCommand,
        )
        from tests.application.test_consultations import fill
        from tests.support.fakes import SequentialCodeGenerator

        fill(seed, _uow(seed), consultation)
        SignConsultation(_uow(seed), SequentialCodeGenerator(), FixedClock()).execute(
            seed.doctor_actor, SignConsultationCommand(consultation_id=consultation.id)
        )

    def test_a_signed_consultation_without_a_visit_is_charged_zero_and_cannot_be_raised(
        self, clinic
    ):
        seed, _ = clinic
        appt, consultation = self._doctors_appointment(seed)

        self._sign(seed, consultation)

        stored = _uow(seed).appointments.get_by_id(appt.id)
        assert stored.status == AppointmentStatus.COMPLETED
        assert (stored.charge.listed, stored.charge.charged) == (fee("0"), fee("0"))
        with pytest.raises(DomainError) as error:
            AdjustAppointmentFee(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), appt.id, fee("5"), "x"
            )
        assert error.value.code == "fee.vaccination_above_list"

    def test_a_signed_consultation_after_a_private_visit_charges_the_doses(self, clinic):
        seed, _ = clinic
        _set(seed, "TD", "25")
        appt, consultation = self._doctors_appointment(seed)
        _visit(seed, appt, _dose("TD"), actor=seed.doctor_actor)

        self._sign(seed, consultation)

        assert _uow(seed).appointments.get_by_id(appt.id).charge.charged == fee("25")

    def test_a_no_show_carries_no_fee(self, clinic):
        from medicore.application.use_cases.appointments import MarkNoShow

        seed, agenda = clinic
        appt = _appointment(seed, agenda, on_today=False)
        MarkNoShow(_uow(seed), FixedClock()).execute(seed.receptionist_actor, appt.id)

        with pytest.raises(DomainError) as error:
            AdjustAppointmentFee(_uow(seed), FixedClock()).execute(
                seed.actor(seed.admin), appt.id, fee("5"), "x"
            )

        assert error.value.code == "fee.vaccination_unpriced"


class TestSetPriceIsIdempotent:
    def test_the_same_price_or_removing_a_missing_one_writes_and_audits_nothing(self, clinic):
        seed, _ = clinic
        _set(seed, "TD", "10")
        before = len(_uow(seed).audit.query(action="vaccine_price.updated"))

        _set(seed, "TD", "10")
        _set(seed, "INFLU", None)

        assert len(_uow(seed).audit.query(action="vaccine_price.updated")) == before
