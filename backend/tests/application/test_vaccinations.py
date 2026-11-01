"""Vaccination use cases: card, recording rules, voiding, worklist and permissions."""

from __future__ import annotations

from datetime import date

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.use_cases.vaccinations import (
    GetVaccinationCard,
    GetVaccinationWorklist,
    RecordVaccination,
    RecordVaccinationCommand,
    VoidVaccination,
)
from medicore.domain.enums import (
    PatientStatus,
    Sex,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
)
from medicore.domain.shared.errors import DomainError, PermissionDenied
from tests.support.builders import build_patient, seed_clinic
from tests.support.fakes import FixedClock

TODAY = date(2026, 5, 31)  # FixedClock default


def _uow(seed):
    return seed.factory.for_tenant(seed.tenant.id)


def _infant(seed, birth=date(2026, 1, 15)):
    baby = build_patient(seed.tenant.id, code="P-00200", first_name="Mateo",
                         last_name="Cruz", sex=Sex.MALE, date_of_birth=birth)
    _uow(seed).patients.save(baby)
    return baby


def _record(seed, actor, patient, **kw):
    cmd = RecordVaccinationCommand(
        patient_id=patient.id,
        vaccine_code=kw.pop("vaccine", "HEXA"),
        dose_key=kw.pop("dose", "HEXA-1"),
        outcome=kw.pop("outcome", VaccinationOutcome.ADMINISTERED),
        occurred_on=kw.pop("on", TODAY),
        source=kw.pop("source", VaccinationSource.CLINIC),
        lot=kw.pop("lot", "L-2231"),
        **kw,
    )
    return RecordVaccination(_uow(seed), FixedClock()).execute(actor, cmd)


def test_nurse_records_a_dose_with_default_route_and_audit():
    seed = seed_clinic()
    baby = _infant(seed)
    rec = _record(seed, seed.actor(seed.nurse), baby)

    assert rec.route == VaccineRoute.INTRAMUSCULAR  # the vaccine's usual route
    card = GetVaccinationCard(_uow(seed), FixedClock()).execute(seed.doctor_actor, baby.id)
    states = {s.dose.key: s for s in card.states}
    assert states["HEXA-1"].status == "administered"
    assert states["HEXA-1"].last_on == TODAY
    actions = [a.action for a in seed.factory.store.audit.values()]
    assert "vaccination.recorded" in actions


def test_dose_given_here_needs_a_lot_but_external_ones_do_not():
    seed = seed_clinic()
    baby = _infant(seed)
    with pytest.raises(DomainError) as exc:
        _record(seed, seed.actor(seed.nurse), baby, lot=None)
    assert exc.value.code == "vaccination.lot_required"
    rec = _record(seed, seed.actor(seed.nurse), baby, lot=None,
                  source=VaccinationSource.EXTERNAL, route=VaccineRoute.ORAL)
    assert rec.lot is None and rec.route is None  # route only describes doses given here


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"vaccine": "NOPE", "dose": None}, "vaccination.unknown_vaccine"),
        ({"vaccine": "SPR", "dose": "HEXA-1"}, "vaccination.dose_mismatch"),
        ({"on": date(2026, 6, 1)}, "vaccination.future_date"),
        ({"on": date(2025, 12, 1)}, "vaccination.before_birth"),
    ],
)
def test_invalid_records_are_rejected(kw, code):
    seed = seed_clinic()
    baby = _infant(seed)
    with pytest.raises(ValidationError) as exc:
        _record(seed, seed.actor(seed.nurse), baby, **kw)
    assert exc.value.code == code


def test_a_one_off_dose_cannot_be_given_twice_unless_voided():
    seed = seed_clinic()
    baby = _infant(seed)
    first = _record(seed, seed.actor(seed.nurse), baby)
    with pytest.raises(ValidationError) as exc:
        _record(seed, seed.actor(seed.nurse), baby)
    assert exc.value.code == "vaccination.dose_already_recorded"

    VoidVaccination(_uow(seed), FixedClock()).execute(
        seed.actor(seed.nurse), first.id, "Lote equivocado"
    )
    _record(seed, seed.actor(seed.nurse), baby, lot="L-9000")  # now allowed
    card = GetVaccinationCard(_uow(seed), FixedClock()).execute(seed.doctor_actor, baby.id)
    assert len(card.records) == 2 and sum(r.is_voided for r in card.records) == 1


def test_void_requires_reason_and_happens_once():
    seed = seed_clinic()
    baby = _infant(seed)
    rec = _record(seed, seed.actor(seed.nurse), baby)
    use_case = VoidVaccination(_uow(seed), FixedClock())
    with pytest.raises(DomainError) as exc:
        use_case.execute(seed.actor(seed.nurse), rec.id, "   ")
    assert exc.value.code == "vaccination.void_reason_required"
    use_case.execute(seed.actor(seed.nurse), rec.id, "Error de registro")
    with pytest.raises(DomainError) as exc:
        use_case.execute(seed.actor(seed.nurse), rec.id, "otra vez")
    assert exc.value.code == "vaccination.already_voided"


def test_inactive_patients_cannot_get_new_records():
    seed = seed_clinic()
    baby = _infant(seed)
    baby.status = PatientStatus.INACTIVE
    _uow(seed).patients.save(baby)
    with pytest.raises(ValidationError) as exc:
        _record(seed, seed.actor(seed.nurse), baby)
    assert exc.value.code == "vaccination.patient_inactive"


def test_receptionist_and_admin_see_but_cannot_record():
    seed = seed_clinic()
    baby = _infant(seed)
    # Recording a dose is a clinical act: neither reception nor the admin does it by default.
    for actor in (seed.receptionist_actor, seed.actor(seed.admin)):
        GetVaccinationCard(_uow(seed), FixedClock()).execute(actor, baby.id)
        with pytest.raises(PermissionDenied):
            _record(seed, actor, baby)


def test_worklist_lists_pending_upcoming_and_given_today():
    seed = seed_clinic()
    baby = _infant(seed)  # 4.5 months old: HEXA-1/2, ROTA-1/2, PCV13-1/2 due by now
    _record(seed, seed.actor(seed.nurse), baby)  # HEXA-1 today

    wl = GetVaccinationWorklist(_uow(seed), FixedClock()).execute(seed.actor(seed.nurse), 60)

    pending = {(i.patient.code, i.state.dose.key) for i in wl.pending}
    assert ("P-00200", "HEXA-2") in pending
    assert ("P-00200", "HEXA-1") not in pending
    assert ("P-00200", "HEXA-3") in {(i.patient.code, i.state.dose.key) for i in wl.upcoming}
    assert [p.code for p, _ in wl.given_today] == ["P-00200"]
    # The adult seed patient: Td never recorded → pending; no childhood doses chased.
    adult = {i.state.dose.key for i in wl.pending if i.patient.code == seed.patient.code}
    assert adult == {"TD-1"}
