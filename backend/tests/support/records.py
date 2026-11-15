"""Signed records written straight into the in-memory store, for tests of lists and reads."""

from __future__ import annotations

from datetime import datetime

from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import ClinicalRecordType
from medicore.domain.shared.identifiers import RecordId
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.vitals import Vitals
from tests.support.builders import soap_note


def sealed(record: MedicalRecord, previous: MedicalRecord | None = None) -> MedicalRecord:
    """The record with the seal a real signature gives it, chained to ``previous``'s."""
    return record.sealed(previous.seal if previous else None)


def store_record(
    seed,
    *,
    code: str,
    encounter_at: datetime,
    patient=None,
    type: ClinicalRecordType = ClinicalRecordType.CONSULTATION,
    chief_complaint: str = "Fiebre",
    vitals: Vitals | None = None,
    signer=None,
) -> MedicalRecord:
    patient = patient or seed.patient
    signer = signer or seed.doctor
    record = sealed(MedicalRecord(
        id=RecordId.new(), tenant_id=seed.tenant.id, code=code, patient_id=patient.id,
        author_id=signer.id, type=type, encounter_at=encounter_at, location_name="Sede",
        chief_complaint=chief_complaint, note=soap_note("s", "o", "a", "plan secreto"),
        vitals=vitals or Vitals(), signed_at=encounter_at, signed_by_id=signer.id,
        diagnoses=(IcdCode("J06.9", "Infección"),),
    ))
    seed.factory.store.medical_records[record.id.value] = record
    return record
