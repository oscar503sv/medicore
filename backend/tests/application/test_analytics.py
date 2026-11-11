"""Practice metrics: what each tier shows, who sees which scope, and who sees the money.
Also the clinic's practice model, which moves the default permissions on fees and income."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from medicore.application.common.entitlements import granted_permissions
from medicore.application.common.errors import ValidationError
from medicore.application.common.permissions import ROLE_PERMISSIONS, Permission
from medicore.application.use_cases.analytics import (
    AnalyticsQuery,
    GetAnalyticsOverview,
    resolve_period,
)
from medicore.application.use_cases.role_permissions import (
    GetPermissionsMatrix,
    SetPracticeModel,
    UpdateRolePermissions,
)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.insurer import Insurer
from medicore.domain.enums import (
    AddonModule,
    AnalyticsTier,
    AppointmentStatus,
    AppointmentType,
    PracticeModel,
    Role,
)
from medicore.domain.services.plan_catalog import CLINICA, INDEPENDIENTE
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.shared.identifiers import AppointmentId, InsurerId
from medicore.domain.value_objects.fee import Charge, fee
from medicore.domain.value_objects.subscription import Subscription
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock

NOW = datetime(2026, 5, 20, 12, 0)  # a Wednesday


def _appt(seed, start, status=AppointmentStatus.COMPLETED, *, doctor=None, charged="30",
          insurer=None, booked=None):
    a = Appointment(
        id=AppointmentId.new(), tenant_id=seed.tenant.id, code="A-1",
        patient_id=seed.patient.id, doctor_id=(doctor or seed.doctor).id,
        location_id=seed.tenant.primary_location.id, type=AppointmentType.CONSULT,
        scheduled_start=start, duration_minutes=30, reason="Control",
        created_by_id=seed.receptionist.id, status=status, insurance_id=insurer,
        charge=Charge.at_list_price(fee(charged)), created_at=booked or start,
    )
    seed.factory.store.appointments[a.id.value] = a
    return a


def _overview(seed, actor, **query):
    uow = seed.factory.for_tenant(seed.tenant.id)
    return GetAnalyticsOverview(uow, FixedClock(NOW)).execute(actor, AnalyticsQuery(**query))


def _with(actor, *extra):
    return replace(actor, permissions=frozenset(
        str(p) for p in ROLE_PERMISSIONS[actor.role] | set(extra)))


def _plan(seed, code, modules=frozenset()):
    seed.tenant.subscription = Subscription(plan_code=code, modules=modules)


@pytest.fixture
def clinic():
    seed = seed_clinic()
    other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@x.test")
    seed.factory.store.users[other.id.value] = other
    insurer = Insurer(id=InsurerId.new(), tenant_id=seed.tenant.id, name="Aseguradora Azul")
    seed.factory.store.insurers[insurer.id.value] = insurer
    _appt(seed, datetime(2026, 5, 4, 9), insurer=insurer.id)
    _appt(seed, datetime(2026, 5, 6, 9), AppointmentStatus.NO_SHOW)
    _appt(seed, datetime(2026, 5, 7, 9), doctor=other, charged="50")
    _appt(seed, datetime(2026, 4, 8, 9))  # last month, same days
    _appt(seed, datetime(2026, 4, 28, 9))  # last month, past "today"'s day: not compared
    seed.other = other
    return seed


class TestPeriods:
    def test_month_to_date_against_the_same_days_last_month(self):
        p = resolve_period(date(2026, 5, 20), AnalyticsTier.CLINIC, AnalyticsQuery())
        assert (p.start, p.end) == (date(2026, 5, 1), date(2026, 5, 20))
        assert (p.previous_start, p.previous_end) == (date(2026, 4, 1), date(2026, 4, 20))

    def test_previous_end_is_clamped_to_a_shorter_month(self):
        p = resolve_period(date(2026, 3, 31), AnalyticsTier.CLINIC, AnalyticsQuery())
        assert p.previous_end == date(2026, 2, 28)

    def test_week_to_date(self):
        p = resolve_period(date(2026, 5, 20), AnalyticsTier.CLINIC, AnalyticsQuery("week"))
        assert (p.start, p.previous_start, p.previous_end) == (
            date(2026, 5, 18), date(2026, 5, 11), date(2026, 5, 13))

    def test_range_is_compared_with_the_days_before(self):
        p = resolve_period(date(2026, 5, 20), AnalyticsTier.CLINIC,
                           AnalyticsQuery("range", date(2026, 3, 1), date(2026, 3, 10)))
        assert (p.previous_start, p.previous_end) == (date(2026, 2, 19), date(2026, 2, 28))

    @pytest.mark.parametrize("start,end", [
        (None, None), (date(2026, 3, 10), date(2026, 3, 1)), (date(2025, 1, 1), date(2026, 3, 1)),
    ])
    def test_invalid_ranges(self, start, end):
        with pytest.raises(ValidationError) as e:
            resolve_period(date(2026, 5, 20), AnalyticsTier.CLINIC,
                           AnalyticsQuery("range", start, end))
        assert e.value.code == "analytics.invalid_range"

    def test_basic_tier_always_gets_the_month(self):
        p = resolve_period(date(2026, 5, 20), AnalyticsTier.BASIC, AnalyticsQuery("week"))
        assert p.kind == "month"


class TestScopeAndMoney:
    def test_doctor_sees_own_figures_with_income(self, clinic):
        o = _overview(clinic, clinic.doctor_actor)
        assert (o.scope, o.money, o.doctor_id) == ("own", True, str(clinic.doctor.id))
        assert (o.current.attended, o.current.no_shows) == (1, 1)
        assert o.current.income == Decimal("30")
        assert o.previous.attended == 1
        assert o.doctors is None  # no per-doctor table in the own scope

    def test_admin_sees_the_clinic_without_money_by_default(self, clinic):
        o = _overview(clinic, clinic.actor(clinic.admin))
        assert (o.scope, o.money) == ("clinic", False)
        assert o.current.attended == 2
        assert o.current.income is None
        assert {r.name: r.totals.attended for r in o.doctors} == {
            "Dra. Elena Ruiz": 1, "Dr. Otro": 1}
        assert all(r.totals.income is None for r in o.doctors)
        assert all(t.income is None for t in o.trend)

    def test_money_permission_adds_income(self, clinic):
        admin = _with(clinic.actor(clinic.admin), Permission.ANALYTICS_MONEY)
        o = _overview(clinic, admin)
        assert o.current.income == Decimal("80")
        insurers = {r.label: (r.attended, r.income) for r in o.insurers}
        assert insurers == {"Aseguradora Azul": (1, Decimal("30")), None: (1, Decimal("50"))}

    def test_clinic_scope_can_narrow_to_one_doctor(self, clinic):
        o = _overview(clinic, clinic.actor(clinic.admin), doctor_id=clinic.other.id)
        assert o.current.attended == 1 and o.doctors is None
        assert o.doctor_id == str(clinic.other.id)

    def test_own_scope_ignores_another_doctor_filter(self, clinic):
        o = _overview(clinic, clinic.doctor_actor, doctor_id=clinic.other.id)
        assert o.doctor_id == str(clinic.doctor.id)

    @pytest.mark.parametrize("who", ["receptionist", "nurse"])
    def test_staff_without_metrics_permissions_is_refused(self, clinic, who):
        with pytest.raises(PermissionDenied) as e:
            _overview(clinic, clinic.actor(getattr(clinic, who)))
        assert e.value.code == "analytics.not_allowed"


class TestTiers:
    def test_basic_tier_has_only_the_month_summary(self, clinic):
        _plan(clinic, INDEPENDIENTE)
        o = _overview(clinic, clinic.doctor_actor, period="week")
        assert o.tier == AnalyticsTier.BASIC and o.period.kind == "month"
        assert (o.trend, o.types, o.insurers, o.operations) == (None, None, None, None)

    def test_clinic_tier_adds_trend_and_breakdowns_but_not_operations(self, clinic):
        _plan(clinic, CLINICA)
        o = _overview(clinic, clinic.doctor_actor)
        assert o.tier == AnalyticsTier.CLINIC
        assert len(o.trend) == 12 and o.types and o.operations is None

    def test_addon_raises_to_operations(self, clinic):
        _plan(clinic, CLINICA, frozenset({AddonModule.ANALYTICS, AddonModule.VACCINATION}))
        o = _overview(clinic, clinic.doctor_actor)
        assert o.tier == AnalyticsTier.OPERATIONS
        assert o.operations.modules.vaccinations == 0
        assert o.operations.modules.procedures is None  # module not contracted
        assert {(c.weekday, c.hour) for c in o.operations.heatmap} == {(0, 9), (2, 9)}


class TestPracticeModel:
    def test_employed_moves_fees_and_money_to_the_administration(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        matrix = SetPracticeModel(uow, FixedClock()).execute(admin, PracticeModel.EMPLOYED)
        assert matrix.practice_model == PracticeModel.EMPLOYED
        doctor = matrix.roles[Role.DOCTOR]
        assert "fees.manage_own" not in doctor.effective
        assert "analytics.money" not in doctor.effective and "analytics.own" in doctor.effective
        assert "analytics.money" in matrix.roles[Role.ADMIN].effective
        tenant = uow.tenants.get_by_id(seed.tenant.id)
        assert Permission.ANALYTICS_MONEY in granted_permissions(uow, tenant, seed.admin)
        assert Permission.FEES_MANAGE_OWN not in granted_permissions(uow, tenant, seed.doctor)
        actions = [e.action for e in uow.audit.list().items]
        assert "organization.practice_model_changed" in actions

    def test_customized_roles_keep_their_customization(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        custom = sorted(str(p) for p in ROLE_PERMISSIONS[Role.DOCTOR]
                        - {Permission.PATIENTS_ARCHIVE})
        UpdateRolePermissions(uow, FixedClock()).execute(admin, Role.DOCTOR, custom)
        SetPracticeModel(uow, FixedClock()).execute(admin, PracticeModel.EMPLOYED)
        doctor = GetPermissionsMatrix(uow).execute(admin).roles[Role.DOCTOR]
        assert "patients.archive" not in doctor.effective
        assert "fees.manage_own" not in doctor.effective
        # Back to associated: the shift is undone, the customization stays.
        doctor = SetPracticeModel(uow, FixedClock()).execute(
            admin, PracticeModel.ASSOCIATED).roles[Role.DOCTOR]
        assert "fees.manage_own" in doctor.effective
        assert "patients.archive" not in doctor.effective

    def test_only_who_manages_permissions(self):
        seed = seed_clinic()
        with pytest.raises(PermissionDenied):
            SetPracticeModel(seed.factory.for_tenant(seed.tenant.id), FixedClock()).execute(
                seed.doctor_actor, PracticeModel.EMPLOYED)
