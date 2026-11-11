"""Integration test: the business-overview queries of the platform read model (GROUP BY
per clinic, distinct people, date_trunc per week) against PostgreSQL. One outer
transaction rolled back at the end; SKIP when PostgreSQL is unreachable.

The database may hold other clinics (the demo), so assertions look at this test's clinic
and at dates no other data uses.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.domain.entities.subscription_payment import SubscriptionPayment
from medicore.domain.enums import PaymentMethod, Role, UserStatus
from medicore.domain.shared.identifiers import PlatformAdminId, SubscriptionPaymentId
from medicore.domain.value_objects.money import Money
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.persistence.models.medical_record import MedicalRecordModel
from medicore.infrastructure.persistence.repositories.other import SqlAuditLogRepository
from medicore.infrastructure.persistence.repositories.platform_reads import SqlPlatformReadModel
from medicore.infrastructure.persistence.repositories.subscription import (
    SqlSubscriptionPaymentRepository,
)
from medicore.infrastructure.persistence.repositories.tenant import SqlTenantRepository
from medicore.infrastructure.persistence.repositories.user import SqlUserRepository
from tests.support.builders import build_tenant, build_user

FUTURE = datetime(2031, 3, 5, 12, 0, tzinfo=UTC)  # a Wednesday no other data reaches


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("PostgreSQL not available")
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    yield session
    session.close()
    trans.rollback()
    connection.close()


@pytest.fixture
def clinic(session):
    tenant = build_tenant(f"biz-{uuid.uuid4().hex[:10]}")
    SqlTenantRepository(session).save(tenant)
    session.flush()
    users = SqlUserRepository(session, tenant.id)
    doctor = build_user(tenant.id, Role.DOCTOR, email="doc@biz.test")
    nurse = build_user(tenant.id, Role.NURSE, email="nurse@biz.test")
    gone = build_user(tenant.id, Role.NURSE, email="gone@biz.test")
    gone.status = UserStatus.SUSPENDED
    for user in (doctor, nurse, gone):
        users.save(user)
    session.flush()
    return tenant, doctor, nurse


def test_active_staff_by_tenant(session, clinic):
    tenant, *_ = clinic
    staff = SqlPlatformReadModel(session).active_staff_by_tenant()
    assert staff[str(tenant.id)] == {"doctor": 1, "nurse": 1}


def test_tenant_counts(session, clinic):
    tenant, *_ = clinic
    counts = SqlPlatformReadModel(session).tenant_counts(tenant.id)
    assert counts == {
        "patients": 0, "users": 3, "appointments": 0, "consultations": 0, "records": 0
    }


def test_payments_since(session, clinic):
    tenant, *_ = clinic
    repo = SqlSubscriptionPaymentRepository(session, tenant.id)
    for paid_on in (date(2031, 3, 1), date(2031, 1, 15)):
        repo.save(SubscriptionPayment(
            id=SubscriptionPaymentId.new(), tenant_id=tenant.id,
            amount=Money(Decimal("79"), "USD"), paid_on=paid_on, months=1, plan_code="clinica",
            period_end=paid_on + timedelta(days=30), method=PaymentMethod.CASH,
            recorded_by=PlatformAdminId.new(), recorded_at=FUTURE,
        ))
    session.flush()
    rows = SqlPlatformReadModel(session).payments_since(date(2031, 2, 1))
    assert [(r.tenant_id, r.amount, r.paid_on) for r in rows] == [
        (str(tenant.id), Decimal("79.00"), date(2031, 3, 1))
    ]


def test_activity_and_weekly_signed(session, clinic):
    tenant, doctor, nurse = clinic
    audit = SqlAuditLogRepository(session, tenant.id)
    for user, when in ((doctor, FUTURE), (nurse, FUTURE - timedelta(days=2)),
                       (doctor, FUTURE - timedelta(days=30))):
        actor = ActorContext(user_id=user.id, tenant_id=tenant.id, role=user.role)
        audit.append(audit_entry(actor, when, "auth.login", "User", str(user.id)))
    for n, signed in enumerate((FUTURE, FUTURE - timedelta(days=1), FUTURE - timedelta(days=8))):
        session.add(MedicalRecordModel(
            id=uuid.uuid4(), tenant_id=tenant.id.value, code=f"REC-BIZ-{n}",
            patient_id=uuid.uuid4(), author_id=doctor.id.value, type="consultation",
            status="signed", encounter_at=signed, location_name="Sede", chief_complaint="x",
            signed_at=signed, signed_by_id=doctor.id.value,
        ))
    session.flush()

    reads = SqlPlatformReadModel(session)
    activity = reads.activity_by_tenant(FUTURE - timedelta(days=7), FUTURE - timedelta(days=7))
    mine = activity[str(tenant.id)]
    assert mine.last_activity == FUTURE
    assert mine.active_users == 2
    assert mine.signed_records == 2

    weeks = dict(reads.signed_per_week(FUTURE - timedelta(days=14)))
    assert weeks == {date(2031, 3, 3): 2, date(2031, 2, 24): 1}
