"""Vaccine prices and priced doses against real PostgreSQL: storage, CHECKs and the dose lock.

Same harness as the other SQL tests: skipped when PostgreSQL is unreachable, rolled back.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import medicore.infrastructure.persistence.models  # noqa: F401  (register all tables)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.vaccination_record import VaccinationRecord
from medicore.domain.entities.vaccine_price import VaccinePrice
from medicore.domain.enums import (
    AppointmentType,
    Role,
    VaccinationOutcome,
    VaccinationSource,
    VaccineSupply,
)
from medicore.domain.shared.identifiers import AppointmentId, VaccinationRecordId
from medicore.domain.value_objects.fee import ZERO, Charge, fee
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.builders import build_patient, build_tenant, build_user

NOW = datetime(2026, 6, 5, 18, 0, tzinfo=UTC)
DAY = date(2026, 6, 5)


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
    Base.metadata.create_all(bind=connection)
    session = Session(bind=connection, expire_on_commit=False)
    yield session
    session.close()
    trans.rollback()
    connection.close()


class Setup:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tenant = build_tenant(slug=f"test-vp-{uuid.uuid4().hex[:8]}")
        self.uow = SqlAlchemyUnitOfWork(session, self.tenant.id)
        self.uow.tenants.save(self.tenant)
        session.flush()
        self.nurse = build_user(self.tenant.id, Role.NURSE, email=f"n{uuid.uuid4().hex[:6]}@v.test")
        self.doctor = build_user(
            self.tenant.id, Role.DOCTOR, email=f"d{uuid.uuid4().hex[:6]}@v.test"
        )
        self.patient = build_patient(self.tenant.id, code="P-00001")
        for entity, repo in ((self.nurse, "users"), (self.doctor, "users"),
                             (self.patient, "patients")):
            getattr(self.uow, repo).save(entity)
        session.flush()

    def appointment(self, charge: Charge | None = None) -> Appointment:
        appointment = Appointment(
            id=AppointmentId.new(), tenant_id=self.tenant.id, code="A-1",
            patient_id=self.patient.id, doctor_id=self.doctor.id,
            location_id=self.tenant.primary_location.id, type=AppointmentType.VACCINATION,
            scheduled_start=datetime(2026, 6, 5, 9), duration_minutes=15, reason="Vacunas",
            created_by_id=self.nurse.id, charge=charge or Charge(),
        )
        self.uow.appointments.save(appointment)
        self.session.flush()
        return appointment

    def dose(self, **kw) -> VaccinationRecord:
        base = dict(
            id=VaccinationRecordId.new(), tenant_id=self.tenant.id,
            patient_id=self.patient.id, vaccine_code="TD", dose_key=None,
            outcome=VaccinationOutcome.ADMINISTERED, occurred_on=DAY,
            source=VaccinationSource.CLINIC, recorded_by_id=self.nurse.id, lot="L-1",
            supply=VaccineSupply.CLINIC, created_at=NOW,
        )
        base.update(kw)
        return VaccinationRecord(**base)

    def refuses(self, statement: str, **params) -> str:
        """Run an invalid statement; returns the violated constraint's name."""
        with pytest.raises(IntegrityError) as error, self.session.begin_nested():
            self.session.execute(text(statement), params)
        return str(error.value.orig)


@pytest.fixture
def db(session):
    return Setup(session)


class TestPrices:
    def test_upsert_list_and_delete(self, db):
        repo = db.uow.vaccine_prices
        repo.save(VaccinePrice(db.tenant.id, "TD", fee("10"), NOW))
        repo.save(VaccinePrice(db.tenant.id, "TD", fee("12.50"), NOW))
        repo.save(VaccinePrice(db.tenant.id, "BCG", ZERO, NOW))
        db.session.expire_all()

        assert repo.as_map() == {"TD": fee("12.50"), "BCG": ZERO}
        assert [p.vaccine_code for p in repo.list()] == ["BCG", "TD"]

        repo.delete("TD")
        repo.delete("TD")  # idempotent

        assert set(repo.as_map()) == {"BCG"}

    def test_get_for_update_reads_the_price(self, db):
        db.uow.vaccine_prices.save(VaccinePrice(db.tenant.id, "TD", fee("10"), NOW))

        assert db.uow.vaccine_prices.get_for_update("TD").price == fee("10")
        assert db.uow.vaccine_prices.get_for_update("BCG") is None

    def test_prices_are_per_clinic(self, db, session):
        other = Setup(session)
        db.uow.vaccine_prices.save(VaccinePrice(db.tenant.id, "TD", fee("10"), NOW))

        assert other.uow.vaccine_prices.as_map() == {}

    def test_the_range_is_checked_in_the_database(self, db):
        message = db.refuses(
            "INSERT INTO vaccine_prices (tenant_id, vaccine_code, price) VALUES (:t, 'TD', -1)",
            t=db.tenant.id.value,
        )

        assert "ck_vaccine_prices_range" in message


class TestDoses:
    def test_supply_and_price_round_trip(self, db):
        appointment = db.appointment()
        dose = db.dose(appointment_id=appointment.id, listed_fee=fee("25"))
        db.uow.vaccinations.save(dose)
        db.session.flush()
        db.session.expunge_all()

        loaded = db.uow.vaccinations.get_by_id(dose.id)

        assert (loaded.supply, loaded.listed_fee) == (VaccineSupply.CLINIC, fee("25"))

    def test_a_dose_before_the_field_has_no_supplier(self, db):
        old = db.dose(supply=None, source=VaccinationSource.EXTERNAL, lot=None)
        db.uow.vaccinations.save(old)
        db.session.flush()
        db.session.expunge_all()

        assert db.uow.vaccinations.get_by_id(old.id).supply is None

    def test_get_for_update_returns_the_dose(self, db):
        dose = db.dose()
        db.uow.vaccinations.save(dose)
        db.session.flush()

        assert db.uow.vaccinations.get_for_update(dose.id).id == dose.id
        assert db.uow.vaccinations.get_for_update(VaccinationRecordId.new()) is None

    def _insert(self, db, **cols) -> str:
        base = {
            "id": uuid.uuid4(), "t": db.tenant.id.value, "p": db.patient.id.value,
            "u": db.nurse.id.value, "supply": "clinic", "source": "clinic",
            "outcome": "administered", "fee": None, "appt": None,
        }
        base.update(cols)
        return db.refuses(
            "INSERT INTO vaccination_records (id, tenant_id, patient_id, vaccine_code, outcome,"
            " occurred_on, source, recorded_by_id, supply, listed_fee, appointment_id)"
            " VALUES (:id, :t, :p, 'TD', :outcome, '2026-06-05', :source, :u, :supply, :fee,"
            " :appt)",
            **base,
        )

    def test_supply_must_be_a_known_value(self, db):
        assert "ck_vaccination_records_supply_value" in self._insert(db, supply="other")

    def test_only_a_dose_given_here_has_a_supplier(self, db):
        assert "ck_vaccination_records_supply_scope" in self._insert(db, source="external")
        assert "ck_vaccination_records_supply_scope" in self._insert(db, outcome="refused")

    def test_the_price_is_in_range(self, db):
        appointment = db.appointment()
        message = self._insert(db, fee=10001, appt=appointment.id.value)

        assert "ck_vaccination_records_fee_range" in message

    def test_a_price_needs_a_supplier_and_an_appointment(self, db):
        assert "ck_vaccination_records_fee_needs_visit" in self._insert(db, fee=5)
        appointment = db.appointment()
        message = self._insert(db, fee=5, supply=None, appt=appointment.id.value)
        assert "ck_vaccination_records_fee_needs_visit" in message

    def test_minsal_is_free(self, db):
        appointment = db.appointment()
        message = self._insert(db, supply="minsal", fee=5, appt=appointment.id.value)

        assert "ck_vaccination_records_minsal_free" in message


class TestVisitFeeCap:
    def test_a_vaccination_visit_cannot_be_charged_above_its_doses(self, db):
        appointment = db.appointment(Charge.at_list_price(fee("20")))

        message = db.refuses(
            "UPDATE appointments SET fee = 25 WHERE id = :id", id=appointment.id.value
        )

        assert "ck_appointments_vaccination_fee_cap" in message

    def test_a_discount_is_fine(self, db):
        appointment = db.appointment(Charge.at_list_price(fee("20")))

        db.session.execute(
            text("UPDATE appointments SET fee = 15 WHERE id = :id"), {"id": appointment.id.value}
        )

    def test_other_types_and_legacy_visits_are_not_capped(self, db):
        legacy = db.appointment()  # no listed price

        db.session.execute(
            text("UPDATE appointments SET fee = 99 WHERE id = :id"), {"id": legacy.id.value}
        )
