"""Reports: the rows behind the metrics, with the same scope, money, tier and module gates,
and the audited CSV export."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import ROLE_PERMISSIONS, Permission
from medicore.application.use_cases.reports import (
    ExportReport,
    GetReport,
    ReportQuery,
)
from medicore.domain.entities.application import ApplicationOrder, ApplicationRecord
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.procedure import Procedure
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.enums import (
    AddonModule,
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
from medicore.domain.services.plan_catalog import CLINICA, INDEPENDIENTE
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import (
    ApplicationOrderId,
    ApplicationRecordId,
    AppointmentId,
    InsurerId,
    ProcedureId,
    ProcedureTypeId,
    VaccinationRecordId,
)
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.domain.value_objects.fee import Charge, fee
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock

NOW = datetime(2026, 5, 20, 12, 0)
MAY = (date(2026, 5, 1), date(2026, 5, 31))


def _appt(seed, start, status=AppointmentStatus.COMPLETED, *, doctor=None, charged="30",
          insurer=None, code="A-1"):
    a = Appointment(
        id=AppointmentId.new(), tenant_id=seed.tenant.id, code=code,
        patient_id=seed.patient.id, doctor_id=(doctor or seed.doctor).id,
        location_id=seed.tenant.primary_location.id, type=AppointmentType.CONSULT,
        scheduled_start=start, duration_minutes=30, reason="Dolor de cabeza intenso",
        created_by_id=seed.receptionist.id, status=status, insurance_id=insurer,
        charge=Charge.at_list_price(fee(charged)), created_at=start,
    )
    seed.factory.store.appointments[a.id.value] = a
    return a


def _procedure(seed, performed_at, *, included=False, charged="40"):
    p = Procedure(
        id=ProcedureId.new(), tenant_id=seed.tenant.id, patient_id=seed.patient.id,
        type_id=ProcedureTypeId.new(), type_name="Sutura", performer=ProcedurePerformer.DOCTOR,
        requires_consent=False, source=ProcedureSource.DIRECT, indication="Herida",
        ordered_by_id=seed.doctor.id, created_by_id=seed.doctor.id,
        status=ProcedureStatus.COMPLETED, performed_at=performed_at,
        performed_by_id=seed.doctor.id, charge=Charge.at_list_price(fee(charged)),
        fee_included=included,
    )
    seed.factory.store.procedures[p.id.value] = p
    return p


def _dose(seed, on, *, vaccine="Td", dose_key=None, source=VaccinationSource.CLINIC,
          voided=False):
    v = VaccinationRecord(
        id=VaccinationRecordId.new(), tenant_id=seed.tenant.id, patient_id=seed.patient.id,
        vaccine_code=vaccine, dose_key=dose_key, outcome=VaccinationOutcome.ADMINISTERED,
        occurred_on=on, source=source, recorded_by_id=seed.doctor.id,
        lot="L-1" if source == VaccinationSource.CLINIC else None,
        voided_at=NOW if voided else None,
    )
    seed.factory.store.vaccinations[v.id.value] = v
    return v


def _application(seed, at, outcome=ApplicationOutcome.APPLIED):
    order = ApplicationOrder(
        id=ApplicationOrderId.new(), tenant_id=seed.tenant.id, patient_id=seed.patient.id,
        drug="Diclofenaco", dose="75 mg", route=ApplicationRoute.INTRAMUSCULAR,
        source=ApplicationOrderSource.INTERNAL, starts_at=at, created_by_id=seed.doctor.id,
        ordered_by_id=seed.doctor.id,
    )
    seed.factory.store.application_orders[order.id.value] = order
    r = ApplicationRecord(
        id=ApplicationRecordId.new(), tenant_id=seed.tenant.id, order_id=order.id,
        patient_id=seed.patient.id, dose_number=1, outcome=outcome, recorded_at=at,
        recorded_by_id=seed.doctor.id,
    )
    seed.factory.store.application_records[r.id.value] = r
    return r


def _with(actor, *extra):
    return replace(actor, permissions=frozenset(
        str(p) for p in ROLE_PERMISSIONS[actor.role] | set(extra)))


def _without(actor, *removed):
    return replace(actor, permissions=frozenset(
        str(p) for p in ROLE_PERMISSIONS[actor.role] - set(removed)))


def _report(seed, actor, kind, start=MAY[0], end=MAY[1], doctor_id=None):
    uow = seed.factory.for_tenant(seed.tenant.id)
    return GetReport(uow, FixedClock(NOW)).execute(
        actor, ReportQuery(kind, start, end, doctor_id))


def _col(table, key):
    i = [c.key for c in table.columns].index(key)
    return [row[i] for row in table.rows]


@pytest.fixture
def clinic():
    seed = seed_clinic()
    seed.patient.contact = ContactInfo(phone="7000-1111")
    other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@x.test")
    seed.factory.store.users[other.id.value] = other
    insurer = Insurer(id=InsurerId.new(), tenant_id=seed.tenant.id, name="Aseguradora Azul")
    seed.factory.store.insurers[insurer.id.value] = insurer
    _appt(seed, datetime(2026, 5, 4, 9), insurer=insurer.id, code="A-1")
    _appt(seed, datetime(2026, 5, 6, 9), AppointmentStatus.NO_SHOW, code="A-2")
    _appt(seed, datetime(2026, 5, 7, 9), doctor=other, charged="50", code="A-3")
    _appt(seed, datetime(2026, 5, 8, 9), AppointmentStatus.CANCELLED, doctor=other, code="A-4")
    _appt(seed, datetime(2026, 4, 8, 9), code="A-0")  # outside May
    seed.other = other
    seed.insurer = insurer
    return seed


class TestAppointments:
    def test_rows_in_the_period_oldest_first_without_the_reason(self, clinic):
        r = _report(clinic, clinic.actor(clinic.admin), "appointments")
        assert _col(r.detail, "code") == ["A-1", "A-2", "A-3", "A-4"]
        assert "reason" not in [c.key for c in r.detail.columns]
        assert all("Dolor" not in str(v) for row in r.detail.rows for v in row)
        assert dict(r.summary.rows) == {"completed": 2, "cancelled": 1, "no_show": 1}
        assert _col(r.detail, "insurer")[0] == "Aseguradora Azul"

    def test_money_columns_only_with_analytics_money(self, clinic):
        admin = clinic.actor(clinic.admin)
        assert "charged" not in [c.key for c in _report(clinic, admin, "appointments")
                                 .detail.columns]
        r = _report(clinic, _with(admin, Permission.ANALYTICS_MONEY), "appointments")
        assert _col(r.detail, "charged")[:3] == [Decimal("30"), Decimal("30"), Decimal("50")]

    def test_a_doctor_sees_only_their_own(self, clinic):
        r = _report(clinic, clinic.doctor_actor, "appointments")
        assert (r.scope, _col(r.detail, "code")) == ("own", ["A-1", "A-2"])
        # A doctor cannot widen the scope with the filter.
        r = _report(clinic, clinic.doctor_actor, "appointments", doctor_id=clinic.other.id)
        assert _col(r.detail, "code") == ["A-1", "A-2"]

    def test_clinic_scope_can_narrow_to_one_doctor(self, clinic):
        r = _report(clinic, clinic.actor(clinic.admin), "appointments",
                    doctor_id=clinic.other.id)
        assert _col(r.detail, "code") == ["A-3", "A-4"]

    def test_without_metrics_access(self, clinic):
        with pytest.raises(PermissionDenied) as e:
            _report(clinic, clinic.actor(clinic.receptionist), "appointments")
        assert e.value.code == "report.not_allowed"


class TestIncomeInsurersNoShows:
    def test_income_needs_money(self, clinic):
        with pytest.raises(PermissionDenied) as e:
            _report(clinic, clinic.actor(clinic.admin), "income")
        assert e.value.code == "report.money_required"

    def test_income_adds_procedures_and_marks_the_included_ones(self, clinic):
        _procedure(clinic, datetime(2026, 5, 5, 10))
        _procedure(clinic, datetime(2026, 5, 9, 10), included=True)
        r = _report(clinic, clinic.doctor_actor, "income")
        assert _col(r.detail, "source") == ["visit", "procedure", "procedure_included"]
        assert _col(r.detail, "charged") == [Decimal("30"), Decimal("40"), Decimal("0.00")]
        assert r.summary.rows == [("Dra. Elena Ruiz", 1, 2, Decimal("70"))]

    def test_insurers_summary_lists_out_of_pocket_last(self, clinic):
        admin = _with(clinic.actor(clinic.admin), Permission.ANALYTICS_MONEY)
        r = _report(clinic, admin, "insurers")
        assert r.summary.rows == [("Aseguradora Azul", 1, Decimal("30")),
                                  (None, 1, Decimal("50"))]
        assert _col(r.detail, "code") == ["A-1"]  # only insured visits in the detail

    def test_no_shows_with_the_patient_phone_and_rates_per_doctor(self, clinic):
        r = _report(clinic, clinic.actor(clinic.admin), "no_shows")
        assert _col(r.detail, "code") == ["A-2", "A-4"]
        assert set(_col(r.detail, "phone")) == {"7000-1111"}
        assert sorted(r.summary.rows) == [("Dr. Otro", 2, 0, 1), ("Dra. Elena Ruiz", 2, 1, 0)]


class TestModules:
    def test_vaccinations_count_clinic_doses_by_age_band(self, clinic):
        clinic.patient.date_of_birth = date(2025, 11, 10)  # 5–6 months old in May 2026
        _dose(clinic, date(2026, 5, 3), vaccine="HEXA", dose_key="HEXA-3")
        _dose(clinic, date(2026, 5, 4), vaccine="HEXA", dose_key="HEXA-3",
              source=VaccinationSource.EXTERNAL)  # given elsewhere: not this clinic's
        _dose(clinic, date(2026, 5, 5), voided=True)
        r = _report(clinic, clinic.actor(clinic.admin), "vaccinations")
        assert _col(r.detail, "age") == [5]
        row = dict(zip([c.key for c in r.summary.columns], r.summary.rows[0], strict=True))
        assert (row["vaccine"], row["dose"], row["age_lt1"], row["total"]) == (
            "HEXA", "dose:3", 1, 1)

    def test_procedures_and_applications(self, clinic):
        _procedure(clinic, datetime(2026, 5, 5, 10))
        _application(clinic, datetime(2026, 5, 6, 11))
        _application(clinic, datetime(2026, 5, 6, 12), ApplicationOutcome.REFUSED)
        admin = clinic.actor(clinic.admin)
        assert _report(clinic, admin, "procedures").summary.rows == [("Sutura", 1)]
        r = _report(clinic, admin, "applications")
        assert r.summary.rows == [("Diclofenaco", 1)]
        assert _col(r.detail, "route") == ["im"]

    def test_a_module_report_needs_the_module(self, clinic):
        clinic.tenant.subscription = Subscription(plan_code=CLINICA, modules=frozenset(
            {AddonModule.VACCINATION}))
        with pytest.raises(PermissionDenied) as e:
            _report(clinic, clinic.actor(clinic.admin), "procedures")
        assert e.value.code == "report.module_required"


class TestPeriodsAndExport:
    def test_basic_tier_reports_on_this_month_or_the_last(self, clinic):
        clinic.tenant.subscription = Subscription(plan_code=INDEPENDIENTE)
        admin = clinic.actor(clinic.admin)
        assert _report(clinic, admin, "appointments", date(2026, 4, 1), date(2026, 4, 30))
        with pytest.raises(ValidationError) as e:
            _report(clinic, admin, "appointments", date(2026, 3, 1), date(2026, 3, 31))
        assert e.value.code == "report.range_not_in_plan"

    @pytest.mark.parametrize("start,end", [
        (date(2026, 5, 10), date(2026, 5, 1)), (date(2025, 1, 1), date(2026, 5, 1)),
    ])
    def test_invalid_ranges(self, clinic, start, end):
        with pytest.raises(ValidationError) as e:
            _report(clinic, clinic.actor(clinic.admin), "appointments", start, end)
        assert e.value.code == "report.invalid_range"

    def test_unknown_report(self, clinic):
        with pytest.raises(ValidationError) as e:
            _report(clinic, clinic.actor(clinic.admin), "salaries")
        assert e.value.code == "report.unknown"

    def test_export_is_audited_without_the_rows(self, clinic):
        uow = clinic.factory.for_tenant(clinic.tenant.id)
        ExportReport(uow, FixedClock(NOW)).execute(
            clinic.actor(clinic.admin), ReportQuery("no_shows", *MAY))
        entry = [a for a in clinic.factory.store.audit.values()
                 if a.action == "report.exported"][0]
        assert entry.metadata["rows"] == 2 and entry.metadata["report"] == "no_shows"
        assert "7000-1111" not in str(entry.metadata)

    def test_export_needs_its_permission(self, clinic):
        uow = clinic.factory.for_tenant(clinic.tenant.id)
        doctor = _without(clinic.doctor_actor, Permission.REPORTS_EXPORT)
        with pytest.raises(PermissionDenied):
            ExportReport(uow, FixedClock(NOW)).execute(doctor, ReportQuery("appointments",
                                                                           *MAY))
