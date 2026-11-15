"""Integration tests: medical documents against PostgreSQL (round trip and the key's unique index).

Run in a rolled-back transaction. Skipped when PostgreSQL is unreachable.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.enums import DocumentKind
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.infrastructure.test_consultation_sign_sql import (  # noqa: F401
    NOW,
    _record,
    _save_the_booking,
    clinic_session,
    engine,
)


def _document(clinic) -> MedicalDocument:
    return MedicalDocument.register(
        tenant_id=clinic.tenant.id,
        patient_id=clinic.patient.id,
        file_name="analitica.pdf",
        kind=DocumentKind.LAB,
        mime_type="application/pdf",
        size_bytes=2048,
        uploaded_by_id=clinic.doctor.id,
        uploaded_at=NOW,
    )


def _uow(clinic_session):  # noqa: F811
    clinic, session = clinic_session
    uow = SqlAlchemyUnitOfWork(session, clinic.tenant.id)
    _save_the_booking(uow, session, clinic)
    return clinic, session, uow


def test_a_document_round_trips_with_its_key_and_record(clinic_session):  # noqa: F811
    clinic, session, uow = _uow(clinic_session)
    record = _record(clinic, clinic.consultation.id)
    uow.medical_records.save(record)
    document = _document(clinic)
    document.link_to(record)
    uow.documents.save(document)
    session.flush()
    [stored] = uow.documents.list_by_patient(clinic.patient.id)
    assert stored.storage_key == f"{clinic.tenant.id}/{clinic.patient.id}/{document.id}"
    assert stored.record_id == record.id


def test_another_tenant_does_not_see_the_document(clinic_session):  # noqa: F811
    clinic, session, uow = _uow(clinic_session)
    uow.documents.save(_document(clinic))
    session.flush()
    from medicore.domain.shared.identifiers import TenantId

    other = SqlAlchemyUnitOfWork(session, TenantId.new())
    assert other.documents.list_by_patient(clinic.patient.id) == []


def test_two_documents_cannot_share_a_storage_key(clinic_session):  # noqa: F811
    clinic, session, uow = _uow(clinic_session)
    first, second = _document(clinic), _document(clinic)
    second.storage_key = first.storage_key
    uow.documents.save(first)
    session.flush()
    uow.documents.save(second)
    with pytest.raises(IntegrityError):
        session.flush()
