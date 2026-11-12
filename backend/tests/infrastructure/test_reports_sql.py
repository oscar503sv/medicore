"""Integration tests: the reports read model against PostgreSQL (one outer transaction rolled
back at the end; SKIP when PostgreSQL is unreachable)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from medicore.domain.entities.application import ApplicationOrder, ApplicationRecord
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.procedure import Procedure, ProcedureType
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.enums import (
    ApplicationOrderSource,
    ApplicationOutcome,
    ApplicationRoute,
    AppointmentStatus,
    AppointmentType,
    ProcedurePerformer,
    ProcedureSource,
    ProcedureStatus,
    Role,
    VaccinationOutcome,
    VaccinationSource,
)
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    AppointmentId,
    ProcedureId,
    ProcedureTypeId,
    TenantId,
    VaccinationRecordId,
)
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.domain.value_objects.fee import Charge, fee
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.infrastructure.test_analytics_sql import engine, session  # noqa: F401
from tests.support.builders import build_patient, build_tenant, build_user

NOW = datetime(2026, 5, 20, 15, 0, tzinfo=UTC)
SINCE, UNTIL = datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC)


def test_rows(session):  # noqa: F811
    tenant = build_tenant(slug=f"test-reports-{TenantId.new().value.hex[:8]}")
    uow = SqlAlchemyUnitOfWork(session, tenant.id)
    uow.tenants.save(tenant)
    session.flush()
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@reports.test")
    other = build_user(tenant.id, Role.DOCTOR, email="otro@reports.test")
    for u in (doctor, other):
        uow.users.save(u)
    ana = build_patient(tenant.id, code="P-00001")
    ana.contact = ContactInfo(phone="7000-1111")
    uow.patients.save(ana)
    kind = ProcedureType(id=ProcedureTypeId.new(), tenant_id=tenant.id, name="Sutura",
                         created_at=NOW)
    uow.procedures.save_type(kind)
    session.flush()

    for code, day, status, who in (("A-2", 5, AppointmentStatus.NO_SHOW, doctor),
                                   ("A-1", 4, AppointmentStatus.COMPLETED, doctor),
                                   ("A-3", 6, AppointmentStatus.COMPLETED, other)):
        uow.appointments.save(Appointment(
            id=AppointmentId.new(), tenant_id=tenant.id, code=code, patient_id=ana.id,
            doctor_id=who.id, location_id=tenant.primary_location.id,
            type=AppointmentType.CONSULT, scheduled_start=datetime(2026, 5, day, 9),
            duration_minutes=30, reason="Control", created_by_id=who.id, status=status,
            charge=Charge.at_list_price(fee("30")),
        ))
    uow.procedures.save(Procedure(
        id=ProcedureId.new(), tenant_id=tenant.id, patient_id=ana.id, type_id=kind.id,
        type_name="Sutura", performer=ProcedurePerformer.DOCTOR, requires_consent=False,
        source=ProcedureSource.DIRECT, indication="Herida", ordered_by_id=doctor.id,
        created_by_id=doctor.id, status=ProcedureStatus.COMPLETED, performed_at=NOW,
        performed_by_id=doctor.id, charge=Charge.at_list_price(fee("40")), fee_included=True,
        created_at=NOW,
    ))
    for source, lot in ((VaccinationSource.CLINIC, "L-1"), (VaccinationSource.EXTERNAL, None)):
        uow.vaccinations.save(VaccinationRecord(
            id=VaccinationRecordId.new(), tenant_id=tenant.id, patient_id=ana.id,
            vaccine_code="Td", dose_key=None, outcome=VaccinationOutcome.ADMINISTERED,
            occurred_on=date(2026, 5, 10), source=source, recorded_by_id=doctor.id, lot=lot,
            created_at=NOW,
        ))
    order = ApplicationOrder(
        id=ApplicationOrderId.new(), tenant_id=tenant.id, patient_id=ana.id,
        drug="Diclofenaco", dose="75 mg", route=ApplicationRoute.INTRAMUSCULAR,
        source=ApplicationOrderSource.INTERNAL, starts_at=datetime(2026, 5, 20, 9),
        created_by_id=doctor.id, ordered_by_id=doctor.id, created_at=NOW,
    )
    uow.applications.save_order(order)
    session.flush()
    uow.applications.save_record(ApplicationRecord(
        id=ApplicationRecordId.new(), tenant_id=tenant.id, order_id=order.id,
        patient_id=ana.id, dose_number=1, outcome=ApplicationOutcome.APPLIED, recorded_at=NOW,
        recorded_by_id=doctor.id,
    ))
    session.flush()

    rows = uow.reports.appointment_rows(datetime(2026, 5, 1), datetime(2026, 6, 1))
    assert [r.code for r in rows] == ["A-1", "A-2", "A-3"]  # oldest first
    first = rows[0]
    assert (first.patient_code, first.patient_name, first.patient_phone) == (
        "P-00001", ana.full_name, "7000-1111")
    assert (first.listed, first.charged, first.insurer_id) == (
        Decimal("30.00"), Decimal("30.00"), None)
    assert [r.code for r in uow.reports.appointment_rows(
        datetime(2026, 5, 1), datetime(2026, 6, 1), other.id)] == ["A-3"]

    [proc] = uow.reports.procedure_rows(SINCE, UNTIL)
    assert (proc.type_name, proc.included, proc.charged, proc.listed) == (
        "Sutura", True, None, Decimal("40.00"))
    assert uow.reports.procedure_rows(SINCE, UNTIL, other.id) == []

    [dose] = uow.reports.vaccination_rows(date(2026, 5, 1), date(2026, 5, 31))
    assert (dose.vaccine_code, dose.lot, dose.patient_sex) == ("Td", "L-1", str(ana.sex))

    [applied] = uow.reports.application_rows(SINCE, UNTIL, doctor.id)
    assert (applied.drug, applied.route, applied.dose_number) == ("Diclofenaco", "im", 1)
