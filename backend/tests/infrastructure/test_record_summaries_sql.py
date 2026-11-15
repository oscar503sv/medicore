"""Integration test: the paginated records list against real PostgreSQL.

The JOINs for names, the accent-folded search over the patient's trigram expressions, the
timestamptz range filters and the tenant isolation only exist in SQL. Same harness as the
other SQL tests: skipped when PostgreSQL is unreachable, everything rolled back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.enums import ClinicalRecordType, Role
from medicore.domain.repositories._support import Paging, RecordFilter
from medicore.domain.shared.identifiers import RecordId, TenantId
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.infrastructure.test_patient_search_sql import engine, session  # noqa: F401, F811
from tests.support.builders import build_patient, build_tenant, build_user, soap_note
from tests.support.records import sealed


def _clinic(session, slug_prefix: str):  # noqa: F811
    tenant = build_tenant(slug=f"{slug_prefix}-{TenantId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, name="Dra. Ruiz", email="doc@summaries.test")
    uow.users.save(doctor)
    return tenant, uow, doctor


def _record(tenant, patient, doctor, code, when, kind=ClinicalRecordType.CONSULTATION):
    return sealed(MedicalRecord(
        id=RecordId.new(), tenant_id=tenant.id, code=code, patient_id=patient.id,
        author_id=doctor.id, type=kind, encounter_at=when, location_name="Sede",
        chief_complaint="Control", note=soap_note("s", "o", "a", "p"), vitals=Vitals(),
        signed_at=when, signed_by_id=doctor.id,
    ))


def _at(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 5, day, hour, 0, tzinfo=UTC)


def test_summaries_filter_search_page_and_isolate_tenants(session):  # noqa: F811
    tenant, uow, doctor = _clinic(session, "test-recsum")
    rosa = build_patient(tenant.id, code="P-00001", first_name="Rosa", last_name="Álvarez")
    ramon = build_patient(tenant.id, code="P-00002", first_name="Ramón", last_name="Núñez")
    for p in (rosa, ramon):
        uow.patients.save(p)
    session.flush()
    for rec in (
        _record(tenant, rosa, doctor, "REC-0001", _at(1)),
        _record(tenant, ramon, doctor, "REC-0002", _at(10)),
        _record(tenant, rosa, doctor, "REC-0003", _at(20, 23), ClinicalRecordType.PROCEDURE),
        _record(tenant, rosa, doctor, "REC-0004", _at(21, 0)),
    ):
        uow.medical_records.save(rec)

    other_tenant, other_uow, other_doctor = _clinic(session, "test-recsum-other")
    stranger = build_patient(other_tenant.id, code="P-00001", first_name="Rosa", last_name="Otra")
    other_uow.patients.save(stranger)
    session.flush()
    other_uow.medical_records.save(
        _record(other_tenant, stranger, other_doctor, "REC-9999", _at(5))
    )
    session.flush()

    def codes(**kwargs) -> list[str]:
        page = uow.medical_records.summaries(RecordFilter(**kwargs), Paging())
        return [s.code for s in page.items]

    assert codes() == ["REC-0004", "REC-0003", "REC-0002", "REC-0001"]  # newest first, own clinic
    assert codes(patient_id=str(ramon.id)) == ["REC-0002"]
    assert codes(type="procedure") == ["REC-0003"]
    assert codes(encounter_from=_at(10), encounter_before=_at(21, 0)) == ["REC-0003", "REC-0002"]
    assert codes(search="REC-0002") == ["REC-0002"]
    assert codes(search="p-00002") == ["REC-0002"]
    assert codes(search="ramon nunez") == ["REC-0002"]
    assert codes(search="ALVAREZ") == ["REC-0004", "REC-0003", "REC-0001"]
    assert codes(search="alvarez 0003") == ["REC-0003"]
    assert codes(search="50%") == []  # LIKE wildcards are literal

    page = uow.medical_records.summaries(RecordFilter(), Paging(offset=1, limit=2))
    assert (page.total, page.offset, page.limit) == (4, 1, 2)
    assert [s.code for s in page.items] == ["REC-0003", "REC-0002"]
    first = page.items[1]
    assert first.patient_name == "Ramón Núñez"
    assert first.signed_by_name == "Dra. Ruiz"
    assert first.encounter_at == _at(10)
