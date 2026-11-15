"""Amendments: only the author, always with a reason, a single chain of versions, and the
reads that follow it (lists show the current version, printing resolves to it)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from medicore.application.common.errors import EntityNotFound
from medicore.application.use_cases.certificates import (
    IssueCertificateCommand,
    IssueMedicalCertificate,
    ListMedicalCertificates,
)
from medicore.application.use_cases.patients import GetPatientDetail
from medicore.application.use_cases.printing import PrintCertificate, PrintRecordDocument
from medicore.application.use_cases.records import (
    AmendMedicalRecord,
    GetMedicalRecord,
    ListMedicalRecords,
    ListPatientHistory,
    ListPatientVitals,
    ListRecordVersions,
    RecordQuery,
)
from medicore.domain.enums import CertificateKind, Role
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.errors import (
    InvalidValueObject,
    PermissionDenied,
    RecordSuperseded,
)
from medicore.domain.value_objects.vitals import Vitals
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock
from tests.support.records import store_record

REASON = "Se añade el resultado de laboratorio recibido"
ENCOUNTER = datetime(2026, 5, 20, 9)


class _Clinic:
    def __init__(self) -> None:
        self.seed = seed_clinic()
        self.record = store_record(
            self.seed, code="REC-1", encounter_at=ENCOUNTER, vitals=Vitals(heart_rate=70)
        )
        self.clock = FixedClock()

    def uow(self):
        return self.seed.factory.for_tenant(self.seed.tenant.id)

    @property
    def doctor(self):
        return self.seed.doctor_actor

    def amend(self, record_id=None, actor=None, **kwargs):
        kwargs.setdefault("reason", REASON)
        kwargs.setdefault("chief_complaint", "Fiebre alta")
        return AmendMedicalRecord(self.uow(), self.clock).execute(
            actor or self.doctor, record_id or self.record.id, **kwargs
        )

    def audits(self, action: str):
        return self.uow().audit.query(action=action)


@pytest.fixture
def clinic() -> _Clinic:
    return _Clinic()


class TestAmending:
    def test_the_author_amends_and_the_original_stays_intact(self, clinic):
        amendment = clinic.amend()

        assert amendment.amends_record_id == clinic.record.id
        assert amendment.amendment_reason == REASON
        assert amendment.author_id == clinic.seed.doctor.id
        assert amendment.signed_by_id == clinic.seed.doctor.id
        stored = clinic.uow().medical_records.get_by_id(clinic.record.id)
        assert stored.chief_complaint == "Fiebre"
        assert stored.amendment_reason is None

    def test_the_audit_names_what_changed_and_never_the_reason(self, clinic):
        amendment = clinic.amend(note={"plan": "plan nuevo"})

        [entry] = clinic.audits("record.amended")
        assert entry.entity_id == str(amendment.id)
        assert entry.metadata["amends"] == str(clinic.record.id)
        assert entry.metadata["changed"] == ["chief_complaint", "note.plan"]
        assert entry.metadata["reason_chars"] == len(REASON)
        assert REASON not in str(entry.metadata)

    def test_nobody_is_notified_of_an_amendment(self, clinic):
        clinic.amend()
        assert clinic.seed.factory.store.notifications == {}

    def test_another_doctor_cannot_amend_and_nothing_is_saved_or_audited(self, clinic):
        colleague = build_user(clinic.seed.tenant.id, Role.DOCTOR, name="Dr. Colega", email="c@x.t")
        clinic.seed.factory.store.users[colleague.id.value] = colleague

        with pytest.raises(PermissionDenied) as exc:
            clinic.amend(actor=clinic.seed.actor(colleague))

        assert exc.value.code == "record.not_own"
        assert len(clinic.seed.factory.store.medical_records) == 1
        assert clinic.audits("record.amended") == []

    def test_support_sessions_do_not_reach_clinical_content(self, clinic):
        support = replace(clinic.doctor, impersonated_by=clinic.seed.platform_admin.id)
        with pytest.raises(PermissionDenied) as exc:
            clinic.amend(actor=support)
        assert exc.value.code == "support.clinical_forbidden"

    def test_a_nurse_lacks_the_permission(self, clinic):
        with pytest.raises(PermissionDenied) as exc:
            clinic.amend(actor=clinic.seed.actor(clinic.seed.nurse))
        assert exc.value.code == "permission.missing"

    def test_an_unknown_record_is_not_found(self, clinic):
        with pytest.raises(EntityNotFound):
            clinic.amend(record_id=type(clinic.record.id).new())

    def test_an_amendment_without_changes_is_refused(self, clinic):
        with pytest.raises(InvalidValueObject) as exc:
            clinic.amend(chief_complaint="Fiebre")
        assert exc.value.code == "record.amend_empty"

    def test_a_short_reason_is_refused_with_its_bounds(self, clinic):
        with pytest.raises(InvalidValueObject) as exc:
            clinic.amend(reason="corto")
        assert exc.value.code == "record.amend_reason_invalid"
        assert exc.value.params == {"min": 10, "max": 1000}

    def test_unknown_note_sections_are_refused(self, clinic):
        with pytest.raises(InvalidValueObject) as exc:
            clinic.amend(note={"nope": "x"})
        assert exc.value.code == "note.unknown_section"


class TestChainOfVersions:
    def test_a_replaced_record_cannot_be_amended_again(self, clinic):
        first = clinic.amend()

        with pytest.raises(RecordSuperseded) as exc:
            clinic.amend(chief_complaint="Otra cosa")

        assert exc.value.code == "record.superseded"
        assert exc.value.params == {"current_id": str(first.id)}
        assert len(clinic.seed.factory.store.medical_records) == 2

    def test_the_not_own_check_comes_before_the_superseded_one(self, clinic):
        clinic.amend()
        colleague = build_user(clinic.seed.tenant.id, Role.DOCTOR, name="Dr. C", email="c@x.t")
        clinic.seed.factory.store.users[colleague.id.value] = colleague
        with pytest.raises(PermissionDenied):
            clinic.amend(actor=clinic.seed.actor(colleague))

    def test_the_latest_of_three_versions_can_be_amended(self, clinic):
        first = clinic.amend()
        second = clinic.amend(first.id, chief_complaint="Fiebre y tos")
        with pytest.raises(RecordSuperseded) as exc:
            clinic.amend(first.id, chief_complaint="x")
        assert exc.value.params == {"current_id": str(second.id)}
        assert second.author_id == clinic.record.author_id

    def test_versions_are_listed_oldest_first_from_any_member(self, clinic):
        first = clinic.amend()
        second = clinic.amend(first.id, chief_complaint="Fiebre y tos")

        for start in (clinic.record.id, first.id, second.id):
            versions = ListRecordVersions(clinic.uow(), clinic.clock).execute(clinic.doctor, start)
            assert [v.record.id for v in versions] == [clinic.record.id, first.id, second.id]
            assert [v.version for v in versions] == [1, 2, 3]
            assert [v.is_current for v in versions] == [False, False, True]
            assert versions[1].signer_name == clinic.seed.doctor.name

    def test_listing_versions_is_audited_on_the_current_one(self, clinic):
        first = clinic.amend()
        ListRecordVersions(clinic.uow(), clinic.clock).execute(clinic.doctor, clinic.record.id)

        [entry] = clinic.audits("record.versions_viewed")
        assert entry.entity_id == str(first.id)
        assert entry.metadata["count"] == 2

    def test_only_who_reads_clinical_content_lists_versions(self, clinic):
        with pytest.raises(PermissionDenied):
            ListRecordVersions(clinic.uow(), clinic.clock).execute(
                clinic.seed.actor(clinic.seed.nurse), clinic.record.id
            )

    def test_an_unknown_record_has_no_versions(self, clinic):
        with pytest.raises(EntityNotFound):
            ListRecordVersions(clinic.uow(), clinic.clock).execute(
                clinic.doctor, type(clinic.record.id).new()
            )

    def test_reading_an_old_version_reports_its_successor(self, clinic):
        first = clinic.amend()
        get = GetMedicalRecord(clinic.uow(), clinic.clock)
        assert get.execute(clinic.doctor, clinic.record.id).superseded_by_id == first.id
        assert get.execute(clinic.doctor, first.id).superseded_by_id is None


class TestReadsShowTheCurrentVersion:
    def test_the_records_list_and_its_total(self, clinic):
        first = clinic.amend()
        page = ListMedicalRecords(clinic.uow(), clinic.clock).execute(
            clinic.doctor, RecordQuery(), Paging()
        )
        assert [i.id for i in page.items] == [str(first.id)]
        assert page.total == 1

    def test_the_history(self, clinic):
        first = clinic.amend()
        history = ListPatientHistory(clinic.uow(), clinic.clock).execute(
            clinic.doctor, clinic.seed.patient.id
        )
        assert [r.id for r in history] == [first.id]

    def test_the_vitals_come_once(self, clinic):
        clinic.amend()
        readings = ListPatientVitals(clinic.uow(), clinic.clock).execute(
            clinic.doctor, clinic.seed.patient.id
        )
        assert len(readings) == 1

    def test_the_patient_detail_counts_and_lists_current_versions(self, clinic):
        first = clinic.amend()
        detail = GetPatientDetail(clinic.uow(), clinic.clock).execute(
            clinic.doctor, clinic.seed.patient.id
        )
        assert detail.records_count == 1
        assert [r.id for r in detail.recent_records] == [str(first.id)]
        assert detail.latest_vitals.record_id == first.id


class TestCertificatesFollowTheChain:
    def _issue(self, clinic, record_id, actor=None, at=ENCOUNTER):
        return IssueMedicalCertificate(clinic.uow(), _Codes(), FixedClock(at)).execute(
            actor or clinic.doctor,
            IssueCertificateCommand(
                record_id=record_id, kind=CertificateKind.REST,
                rest_from=date(2026, 5, 20), rest_days=2,
            ),
        )

    def test_issuing_on_a_replaced_record_uses_the_current_one(self, clinic):
        first = clinic.amend()
        certificate = self._issue(clinic, clinic.record.id)
        assert certificate.record_id == first.id

    def test_another_doctor_cannot_certify_the_chain(self, clinic):
        colleague = build_user(clinic.seed.tenant.id, Role.DOCTOR, name="Dr. C", email="c@x.t")
        clinic.seed.factory.store.users[colleague.id.value] = colleague
        clinic.amend()
        with pytest.raises(PermissionDenied) as exc:
            self._issue(clinic, clinic.record.id, actor=clinic.seed.actor(colleague))
        assert exc.value.code == "certificate.not_own"

    def test_listing_by_record_covers_the_whole_chain_newest_first(self, clinic):
        old = self._issue(clinic, clinic.record.id)
        first = clinic.amend()
        later = self._issue(clinic, first.id, at=ENCOUNTER + timedelta(days=3))
        for start in (clinic.record.id, first.id):
            listed = ListMedicalCertificates(clinic.uow()).execute(clinic.doctor, record_id=start)
            assert [c.id for c in listed] == [later.id, old.id]

    def test_the_certificate_prints_the_original_signing_time(self, clinic):
        certificate = self._issue(clinic, clinic.record.id)
        clinic.amend()
        printed = PrintCertificate(clinic.uow(), FixedClock()).execute(
            clinic.doctor, certificate.id
        )
        assert printed.ended_at == clinic.record.signed_at


class TestPrintingResolvesToTheCurrentVersion:
    def _print(self, clinic, record_id):
        return PrintRecordDocument(clinic.uow(), FixedClock()).execute(
            clinic.doctor, record_id, "record"
        )

    def test_an_original_prints_as_version_one(self, clinic):
        doc = self._print(clinic, clinic.record.id)
        assert (doc.version, doc.original_signed_at, doc.amends_code) == (1, None, None)

    def test_a_replaced_id_prints_the_current_version(self, clinic):
        first = clinic.amend()
        second = clinic.amend(first.id, chief_complaint="Fiebre y tos")

        doc = self._print(clinic, clinic.record.id)

        assert doc.record.id == second.id
        assert doc.record.chief_complaint == "Fiebre y tos"
        assert doc.version == 3
        assert doc.original_signed_at == clinic.record.signed_at
        assert doc.amends_code == clinic.record.code
        [entry] = clinic.audits("document.printed")
        assert entry.entity_id == str(second.id)


class _Codes:
    def __init__(self) -> None:
        self._n = 0

    def next_certificate_code(self, day):
        self._n += 1
        return f"CM-{day.year}-{self._n:04d}"
