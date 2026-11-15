"""The integrity seal: a frozen canonical form, a chain that detects any edit, and the
statuses a check reports."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from medicore.domain.entities.medical_document import AttachmentRef
from medicore.domain.entities.medical_record import MedicalRecord, VaccineAdministration
from medicore.domain.entities.prescription import PrescriptionSnapshot
from medicore.domain.enums import (
    ClinicalRecordType,
    DocumentKind,
    ExamKind,
    RecordStatus,
    SealStatus,
)
from medicore.domain.services.record_seal import (
    CURRENT_SEAL_VERSION,
    canonical_v1,
    compute_seal,
    seal_v1,
    verify_chain,
    worst,
)
from medicore.domain.shared.identifiers import (
    AppointmentId,
    ConsultationId,
    DocumentId,
    PatientId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.record_seal import RecordSeal
from medicore.domain.value_objects.vitals import Vitals
from tests.support.builders import soap_note
from tests.support.records import sealed

AT = datetime(2026, 5, 12, 9, 0, tzinfo=UTC)


def _uuid(n: int) -> UUID:
    return UUID(int=n)


def make_record(**overrides) -> MedicalRecord:
    fields = dict(
        id=RecordId(_uuid(1)), tenant_id=TenantId(_uuid(2)), code="REC-2026-0512-CR",
        patient_id=PatientId(_uuid(3)), author_id=UserId(_uuid(4)),
        type=ClinicalRecordType.CONSULTATION, encounter_at=AT, location_name="Sede Central",
        insurer_name="Seguros Ñandú", chief_complaint="Cefalea 🤕 intensa",
        note=soap_note("dolor", "TA elevada", "HTA", "Enalapril"),
        vitals=Vitals(blood_pressure="150/95", heart_rate=88, temperature=Decimal("37.50"),
                      weight=Decimal("70.0")),
        signed_at=AT + timedelta(minutes=30), signed_by_id=UserId(_uuid(5)),
        appointment_id=AppointmentId(_uuid(6)), consultation_id=ConsultationId(_uuid(7)),
        diagnoses=(IcdCode("I10", "Hipertensión esencial"),),
        prescriptions=(PrescriptionSnapshot("Enalapril", "20 mg", "1x día",
                                            date(2026, 5, 12), duration_days=30),),
        vaccines=(VaccineAdministration("Influenza", "L123", "1ª dosis", "Deltoides izq."),),
        exams=(ExamRequest("Hemograma", ExamKind.LAB, "en ayunas"),),
        attachments=(AttachmentRef(DocumentId(_uuid(8)), "lab.pdf", DocumentKind.LAB),),
    )
    return MedicalRecord(**{**fields, **overrides})


def amendment_of(original: MedicalRecord, **overrides) -> MedicalRecord:
    fields = dict(
        id=RecordId(_uuid(9)), status=RecordStatus.AMENDED, amends_record_id=original.id,
        amendment_reason="Se corrige el motivo", chief_complaint="Cefalea tensional",
        signed_at=AT + timedelta(days=1),
    )
    return sealed(replace(original, seal=None, **{**fields, **overrides}), original)


# The digest of ``make_record()`` under version 1. If this test fails, the canonical form
# changed: that would turn every stored seal "tampered". Make a version 2 instead.
GOLDEN_V1 = "5b1af42aa4574d4f74faa3ddc1a9552a3f2e5edad227deb00aa1f88c2581a42d"


def test_golden_vector_of_version_1():
    assert CURRENT_SEAL_VERSION == 1
    assert seal_v1(make_record(), None) == RecordSeal(1, GOLDEN_V1)
    assert compute_seal(make_record(), None) == seal_v1(make_record(), None)


@pytest.mark.parametrize("change", [
    {"id": RecordId(_uuid(100))},
    {"tenant_id": TenantId(_uuid(100))},
    {"code": "REC-2"},
    {"patient_id": PatientId(_uuid(100))},
    {"author_id": UserId(_uuid(100))},
    {"type": ClinicalRecordType.PROCEDURE},
    {"status": RecordStatus.AMENDED},
    {"encounter_at": AT + timedelta(microseconds=1)},
    {"location_name": "Otra sede"},
    {"insurer_name": None},
    {"chief_complaint": "Cefalea intensa"},
    {"note": soap_note("dolor", "TA elevada", "HTA", "Losartán")},
    {"vitals": Vitals(blood_pressure="150/95", heart_rate=89, temperature=Decimal("37.50"),
                      weight=Decimal("70.0"))},
    {"vitals": Vitals(blood_pressure="150/95", heart_rate=88, temperature=Decimal("37.5"),
                      weight=Decimal("70.0"))},
    {"diagnoses": (IcdCode("I10", "Hipertensión"),)},
    {"prescriptions": ()},
    {"vaccines": ()},
    {"exams": ()},
    {"attachments": ()},
    {"signed_at": AT + timedelta(minutes=31)},
    {"signed_by_id": UserId(_uuid(100))},
    {"appointment_id": None},
    {"consultation_id": None},
    {"amends_record_id": RecordId(_uuid(100))},
    {"amendment_reason": "otra razón"},
])
def test_every_sealed_field_changes_the_digest(change):
    assert seal_v1(make_record(**change), None) != seal_v1(make_record(), None)


def test_the_previous_seal_enters_the_digest():
    other = RecordSeal(1, "a" * 64)
    assert seal_v1(make_record(), other) != seal_v1(make_record(), None)
    assert seal_v1(make_record(), other) != seal_v1(make_record(), RecordSeal(1, "b" * 64))


def test_lists_and_tuples_seal_the_same_and_the_seal_does_not_seal_itself():
    record = make_record()
    as_lists = make_record(diagnoses=list(record.diagnoses))
    assert seal_v1(as_lists, None) == seal_v1(record, None)
    assert seal_v1(replace(record, seal=RecordSeal(1, "c" * 64)), None) == seal_v1(record, None)


def test_the_same_instant_in_another_time_zone_seals_the_same():
    el_salvador = timezone(timedelta(hours=-6))
    moved = make_record(encounter_at=AT.astimezone(el_salvador),
                        signed_at=(AT + timedelta(minutes=30)).astimezone(el_salvador))
    assert seal_v1(moved, None) == seal_v1(make_record(), None)


def test_a_naive_instant_is_read_as_utc():
    naive = make_record(encounter_at=AT.replace(tzinfo=None))
    assert seal_v1(naive, None) == seal_v1(make_record(), None)


def test_the_canonical_form_is_compact_sorted_utf8_and_keeps_accents_and_emojis():
    raw = canonical_v1(make_record(), None)
    text = raw.decode("utf-8")
    assert "Cefalea 🤕 intensa" in text and "Seguros Ñandú" in text
    assert ", " not in text and ": " not in text
    assert text.startswith('{"amendment_reason":null,"amends_record_id":null,')
    assert text.endswith('"vitals":{"blood_pressure":"150/95","fetal_heart_rate":null,'
                         '"glucose":null,"heart_rate":88,"height":null,"spo2":null,'
                         '"temperature":"37.50","weight":"70.0"}}')


def test_sealed_returns_the_record_with_its_seal():
    record = make_record()
    assert record.seal is None
    assert record.sealed(None).seal == seal_v1(record, None)


class TestVerifyChain:
    def chain(self):
        original = sealed(make_record())
        first = amendment_of(original)
        second = amendment_of(first, id=RecordId(_uuid(10)), chief_complaint="Cefalea crónica")
        return [original, first, second]

    def test_an_untouched_chain_is_ok(self):
        assert verify_chain(self.chain()) == (SealStatus.OK,) * 3

    def test_an_empty_chain_has_nothing_wrong(self):
        assert verify_chain([]) == ()
        assert worst(()) == SealStatus.OK

    def test_an_altered_record_is_tampered_where_it_happened(self):
        original, first, second = self.chain()
        altered = replace(first, chief_complaint="Otra cosa")
        assert verify_chain([original, altered, second]) == (
            SealStatus.OK, SealStatus.TAMPERED, SealStatus.OK,
        )

    def test_an_altered_original_breaks_the_link_of_the_next_version_too(self):
        original, first, second = self.chain()
        altered = replace(original, location_name="Otra sede")
        statuses = verify_chain([altered, first, second])
        assert statuses[0] == SealStatus.TAMPERED
        assert statuses[1:] == (SealStatus.OK, SealStatus.OK)  # each is checked on its own

    def test_a_record_recomputed_after_editing_breaks_the_next_link(self):
        original, first, second = self.chain()
        edited = sealed(replace(original, seal=None, location_name="Otra sede"))
        assert verify_chain([edited, first, second]) == (
            SealStatus.OK, SealStatus.TAMPERED, SealStatus.OK,
        )

    def test_a_broken_link_is_tampered(self):
        original, first, second = self.chain()
        assert verify_chain([original, second]) == (SealStatus.OK, SealStatus.TAMPERED)

    def test_an_original_that_claims_to_amend_is_tampered(self):
        record = make_record(amends_record_id=RecordId(_uuid(50)), amendment_reason="x")
        assert verify_chain([sealed(record)]) == (SealStatus.TAMPERED,)

    def test_a_record_without_a_seal_is_tampered(self):
        assert verify_chain([make_record()]) == (SealStatus.TAMPERED,)

    def test_an_unknown_version_cannot_be_verified(self):
        record = replace(make_record(), seal=RecordSeal(2, "d" * 64))
        assert verify_chain([record]) == (SealStatus.UNVERIFIABLE,)

    def test_the_worst_status_wins(self):
        assert worst([SealStatus.OK, SealStatus.UNVERIFIABLE]) == SealStatus.UNVERIFIABLE
        assert worst([SealStatus.UNVERIFIABLE, SealStatus.TAMPERED, SealStatus.OK]) == (
            SealStatus.TAMPERED
        )
