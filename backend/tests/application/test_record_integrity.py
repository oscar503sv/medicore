"""Integrity seals at work: reads report and audit a record that no longer matches its seal,
printing flags it without refusing, and an amendment is never sealed on top of it."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

from medicore.application.use_cases.certificates import (
    IssueCertificateCommand,
    IssueMedicalCertificate,
)
from medicore.application.use_cases.printing import PrintCertificate, PrintRecordDocument
from medicore.application.use_cases.records import (
    AmendMedicalRecord,
    GetMedicalRecord,
    ListRecordVersions,
)
from medicore.domain.entities.prescription import Prescription, PrescriptionSnapshot
from medicore.domain.enums import CertificateKind, SealStatus
from medicore.domain.shared.errors import RecordTampered
from medicore.domain.shared.identifiers import PrescriptionId
from medicore.domain.value_objects.record_seal import RecordSeal
from tests.application.test_record_amendments import _Codes
from tests.application.test_records_and_permissions import _sign_a_record
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock
from tests.support.records import sealed, store_record

REASON = "Se añade el resultado de laboratorio recibido"
ENCOUNTER = datetime(2026, 5, 20, 9)


class _Clinic:
    def __init__(self) -> None:
        self.seed = seed_clinic()
        self.record = store_record(self.seed, code="REC-1", encounter_at=ENCOUNTER)
        self.clock = FixedClock()
        self.store = self.seed.factory.store

    def uow(self):
        return self.seed.factory.for_tenant(self.seed.tenant.id)

    @property
    def doctor(self):
        return self.seed.doctor_actor

    def amend(self, record_id=None, **kwargs):
        kwargs.setdefault("reason", REASON)
        kwargs.setdefault("chief_complaint", "Fiebre alta")
        return AmendMedicalRecord(self.uow(), self.clock).execute(
            self.doctor, record_id or self.record.id, **kwargs
        )

    def tamper(self, record, **changes):
        """Edit a stored record behind the application's back, leaving its seal as it was."""
        self.store.medical_records[record.id.value] = replace(record, **changes)

    def audits(self, action: str):
        return self.uow().audit.query(action=action)

    def get(self, record_id):
        return GetMedicalRecord(self.uow(), self.clock).execute(self.doctor, record_id)


@pytest.fixture
def clinic() -> _Clinic:
    return _Clinic()


class TestReadingARecord:
    def test_an_untouched_record_is_ok_and_leaves_no_integrity_trail(self, clinic):
        assert clinic.get(clinic.record.id).integrity == SealStatus.OK
        assert clinic.audits("record.integrity_failed") == []

    def test_an_altered_record_is_shown_as_tampered_and_audited_with_the_viewing(self, clinic):
        clinic.tamper(clinic.record, chief_complaint="Otra cosa")

        view = clinic.get(clinic.record.id)

        assert view.integrity == SealStatus.TAMPERED
        assert view.record.chief_complaint == "Otra cosa"  # shown, with the warning
        [viewed] = clinic.audits("record.viewed")
        [failed] = clinic.audits("record.integrity_failed")
        assert failed.entity_id == str(clinic.record.id)
        assert failed.metadata["versions"] == [str(clinic.record.id)]
        assert "Otra cosa" not in str(failed.metadata)
        assert viewed.entity_id == failed.entity_id

    def test_a_record_resting_on_an_altered_ancestor_is_not_trusted_either(self, clinic):
        first = clinic.amend()
        clinic.tamper(clinic.record, location_name="Otra sede")

        view = clinic.get(first.id)

        assert view.integrity == SealStatus.TAMPERED
        [failed] = clinic.audits("record.integrity_failed")
        assert failed.metadata["versions"] == [str(clinic.record.id)]

    def test_an_altered_later_version_does_not_taint_the_original(self, clinic):
        first = clinic.amend()
        clinic.tamper(first, chief_complaint="Otra cosa")

        assert clinic.get(clinic.record.id).integrity == SealStatus.OK
        assert clinic.get(first.id).integrity == SealStatus.TAMPERED

    def test_an_unknown_seal_version_is_unverifiable(self, clinic):
        clinic.tamper(clinic.record, seal=RecordSeal(2, "e" * 64))
        assert clinic.get(clinic.record.id).integrity == SealStatus.UNVERIFIABLE
        assert len(clinic.audits("record.integrity_failed")) == 1

    def test_versions_report_their_own_integrity_on_top_of_their_ancestors(self, clinic):
        first = clinic.amend()
        second = clinic.amend(first.id, chief_complaint="Fiebre muy alta")
        clinic.tamper(first, chief_complaint="Otra cosa")

        versions = ListRecordVersions(clinic.uow(), clinic.clock).execute(
            clinic.doctor, clinic.record.id
        )

        assert [v.record.id for v in versions] == [clinic.record.id, first.id, second.id]
        assert [v.integrity for v in versions] == [
            SealStatus.OK, SealStatus.TAMPERED, SealStatus.TAMPERED,
        ]
        [failed] = clinic.audits("record.integrity_failed")
        assert failed.metadata["versions"] == [str(first.id)]


class TestAmending:
    def test_an_altered_record_is_not_amended(self, clinic):
        clinic.tamper(clinic.record, chief_complaint="Otra cosa")

        with pytest.raises(RecordTampered) as exc:
            clinic.amend()

        assert exc.value.code == "record.tampered"
        assert len(clinic.store.medical_records) == 1
        assert clinic.audits("record.amended") == []

    def test_a_record_resting_on_an_altered_ancestor_is_not_amended(self, clinic):
        first = clinic.amend()
        clinic.tamper(clinic.record, location_name="Otra sede")
        with pytest.raises(RecordTampered):
            clinic.amend(first.id, chief_complaint="Fiebre muy alta")

    def test_the_amendment_is_chained_and_its_audit_carries_the_seal(self, clinic):
        amendment = clinic.amend()

        assert amendment.seal is not None
        [entry] = clinic.audits("record.amended")
        assert entry.metadata["seal"] == amendment.seal.digest
        assert clinic.get(amendment.id).integrity == SealStatus.OK


class TestSigning:
    def test_the_signed_record_is_sealed_and_the_audit_carries_the_seal(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        record = _sign_a_record(seed, uow)

        stored = seed.factory.store.medical_records[record.id.value]
        assert stored.seal is not None and stored.seal.version == 1
        [entry] = uow.audit.query(action="consultation.signed")
        assert entry.metadata["seal"] == stored.seal.digest
        assert GetMedicalRecord(uow, FixedClock()).execute(
            seed.doctor_actor, record.id
        ).integrity == SealStatus.OK


class TestStoring:
    def test_a_stored_record_is_never_saved_again(self, clinic):
        with pytest.raises(RuntimeError, match="append-only"):
            clinic.uow().medical_records.save(clinic.record)

    def test_an_unsealed_record_is_not_saved(self, clinic):
        with pytest.raises(ValueError, match="sealed"):
            clinic.uow().medical_records.save(
                replace(clinic.record, id=type(clinic.record.id).new(), seal=None)
            )


class TestPrinting:
    def _print(self, clinic, document="record"):
        return PrintRecordDocument(clinic.uow(), clinic.clock).execute(
            clinic.doctor, clinic.record.id, document
        )

    def test_a_sound_record_prints_with_its_seal(self, clinic):
        doc = self._print(clinic)
        assert doc.integrity == SealStatus.OK
        assert doc.seal == clinic.record.seal

    def test_an_altered_record_still_prints_but_says_so_and_is_audited(self, clinic):
        clinic.tamper(clinic.record, chief_complaint="Otra cosa")

        doc = self._print(clinic)

        assert doc.integrity == SealStatus.TAMPERED
        assert len(clinic.audits("document.printed")) == 1
        [failed] = clinic.audits("record.integrity_failed")
        assert failed.metadata["versions"] == [str(clinic.record.id)]

    def test_the_seal_is_checked_before_cancelled_prescriptions_are_left_out(self, clinic):
        record = sealed(replace(clinic.record, seal=None, prescriptions=(
            *clinic.record.prescriptions,
            *_snapshots("Paracetamol", "Ibuprofeno"),
        )))
        clinic.store.medical_records[record.id.value] = record
        uow = clinic.uow()
        snapshot = record.prescriptions[0]
        cancelled = Prescription(
            id=PrescriptionId.new(), tenant_id=clinic.seed.tenant.id,
            patient_id=clinic.seed.patient.id, prescriber_id=clinic.seed.doctor.id,
            drug=snapshot.drug, dose=snapshot.dose, schedule=snapshot.schedule,
            start_date=snapshot.start_date, record_id=record.id,
        )
        cancelled.cancel(clinic.seed.doctor.id, "Allergic reaction reported", ENCOUNTER)
        uow.prescriptions.save(cancelled)

        doc = self._print(clinic, "prescription")

        assert [p.drug for p in doc.record.prescriptions] == ["Ibuprofeno"]
        assert doc.integrity == SealStatus.OK

    def test_a_certificate_carries_the_integrity_of_its_record(self, clinic):
        certificate = IssueMedicalCertificate(
            clinic.uow(), _Codes(), FixedClock(ENCOUNTER)
        ).execute(
            clinic.doctor,
            IssueCertificateCommand(
                record_id=clinic.record.id, kind=CertificateKind.REST,
                rest_from=date(2026, 5, 20), rest_days=2,
            ),
        )
        printer = PrintCertificate(clinic.uow(), clinic.clock)
        assert printer.execute(clinic.doctor, certificate.id).integrity == SealStatus.OK

        clinic.tamper(clinic.record, chief_complaint="Otra cosa")
        assert printer.execute(clinic.doctor, certificate.id).integrity == SealStatus.TAMPERED
        assert len(clinic.audits("record.integrity_failed")) == 1


def _snapshots(*drugs):
    return tuple(PrescriptionSnapshot(d, "500 mg", "c/8 h", date(2026, 5, 20)) for d in drugs)
