"""Integration tests (PostgreSQL): service agendas in the database.

The constraints that keep an appointment attended by exactly one doctor or agenda, the lock
that serializes bookings per agenda, and the visit's appointment lock. Same harness as
``test_appointment_booking_sql``.
"""

from __future__ import annotations

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ConflictError, ValidationError
from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
)
from medicore.application.use_cases.vaccinations import (
    RecordVaccinationVisit,
    RecordVaccinationVisitCommand,
    VisitDose,
)
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.service_agenda import ServiceAgenda
from medicore.domain.enums import AppointmentStatus, AppointmentType, Role, ServiceAgendaKind
from medicore.domain.shared.errors import SlotUnavailable
from medicore.domain.shared.identifiers import AppointmentId, ServiceAgendaId
from medicore.domain.value_objects.assignee import Assignee
from tests.infrastructure.test_consultation_sign_sql import WAIT, Clinic, engine  # noqa: F401
from tests.support.builders import build_weekday_availability
from tests.support.fakes import FixedClock

BOOKING_CLOCK = datetime(2026, 5, 31, 9, 0)
SLOT = datetime(2026, 6, 1, 10, 0)
TODAY_CLOCK = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


def _agenda(clinic: Clinic, name: str = "Vacunatorio") -> ServiceAgenda:
    agenda = ServiceAgenda(
        id=ServiceAgendaId.new(), tenant_id=clinic.tenant.id, name=name,
        kind=ServiceAgendaKind.VACCINATION,
    )
    with Session(bind=clinic.engine) as session:
        uow = clinic.uow(session)
        uow.service_agendas.save(agenda)
        session.flush()
        uow.availability.save(build_weekday_availability(
            clinic.tenant.id, None, slot_minutes=15, agenda_id=agenda.id
        ))
        session.commit()
    return agenda


def _staff(clinic: Clinic, role: Role = Role.RECEPTIONIST) -> ActorContext:
    return ActorContext(user_id=clinic.doctor.id, tenant_id=clinic.tenant.id, role=role)


def _book(clinic: Clinic, agenda: ServiceAgenda) -> None:
    with Session(bind=clinic.engine, expire_on_commit=False) as session:
        uow = clinic.uow(session)
        CreateAppointment(uow, uow.code_generator(), FixedClock(BOOKING_CLOCK)).execute(
            _staff(clinic),
            CreateAppointmentCommand(
                patient_id=clinic.patient.id, doctor_id=None, agenda_id=agenda.id,
                location_id=clinic.tenant.primary_location.id, type=AppointmentType.VACCINATION,
                scheduled_start=SLOT, reason="Vacunas",
            ),
        )


def _vaccination_appointment(clinic: Clinic, agenda: ServiceAgenda) -> Appointment:
    appointment = Appointment(
        id=AppointmentId.new(), tenant_id=clinic.tenant.id, code="A-9",
        patient_id=clinic.patient.id, doctor_id=None, agenda_id=agenda.id,
        location_id=clinic.tenant.primary_location.id, type=AppointmentType.VACCINATION,
        scheduled_start=datetime(2026, 6, 1, 9, 0), duration_minutes=15, reason="Vacunas",
        created_by_id=clinic.doctor.id, status=AppointmentStatus.CONFIRMED,
    )
    with Session(bind=clinic.engine) as session:
        clinic.uow(session).appointments.save(appointment)
        session.commit()
    return appointment


def _visit(clinic: Clinic, appointment: Appointment) -> None:
    with Session(bind=clinic.engine, expire_on_commit=False) as session:
        RecordVaccinationVisit(clinic.uow(session), FixedClock(TODAY_CLOCK)).execute(
            _staff(clinic, Role.NURSE),
            RecordVaccinationVisitCommand(
                appointment_id=appointment.id, patient_id=clinic.patient.id,
                doses=(VisitDose("TD", lot="TD-1"),),
            ),
        )


def _scalar(clinic: Clinic, sql: str, **params):
    with clinic.engine.connect() as conn:
        return conn.execute(text(sql), {"t": clinic.tenant.id.value, **params}).scalar()


def _outcome(future) -> str:
    try:
        future.result(timeout=10)
        return "done"
    except (SlotUnavailable, Exception) as error:  # noqa: BLE001 - the code is asserted below
        return getattr(error, "code", type(error).__name__)


class TestStorage:
    def test_an_agenda_appointment_round_trips_with_no_doctor(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            agenda = _agenda(clinic)
            saved = _vaccination_appointment(clinic, agenda)

            with Session(bind=engine) as session:
                loaded = clinic.uow(session).appointments.get_by_id(saved.id)
                overlapping = clinic.uow(session).appointments.find_overlapping(
                    Assignee.agenda(agenda.id), datetime(2026, 6, 1, 9, 0),
                    datetime(2026, 6, 1, 9, 15),
                )
                of_doctor = clinic.uow(session).appointments.find_overlapping(
                    Assignee.doctor(clinic.doctor.id), datetime(2026, 6, 1, 9, 0),
                    datetime(2026, 6, 1, 9, 15),
                )

            assert loaded.doctor_id is None and loaded.agenda_id == agenda.id
            assert [a.id for a in overlapping] == [saved.id]
            assert saved.id not in [a.id for a in of_doctor]

    def test_the_database_refuses_an_appointment_with_two_or_no_assignee(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            agenda = _agenda(clinic)
            for doctor, agenda_id in ((clinic.doctor.id.value, agenda.id.value), (None, None)):
                with (
                    pytest.raises(IntegrityError, match="ck_appointments_one_assignee"),
                    Session(bind=engine) as session,
                ):
                    session.execute(text(
                        "INSERT INTO appointments (id, tenant_id, code, patient_id, "
                        "doctor_id, agenda_id, location_id, type, status, scheduled_start, "
                        "duration_minutes, reason, created_by_id) VALUES (:id, :t, 'A-X', "
                        ":p, :d, :a, :l, 'vaccination', 'scheduled', now(), 15, 'x', :c)"
                    ), {"id": uuid.uuid4(), "t": clinic.tenant.id.value,
                        "p": clinic.patient.id.value, "d": doctor, "a": agenda_id,
                        "l": clinic.tenant.primary_location.id.value,
                        "c": clinic.doctor.id.value})
                    session.commit()

    def test_a_schedule_needs_exactly_one_owner_and_one_per_agenda(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            agenda = _agenda(clinic)

            with (
                pytest.raises(IntegrityError, match="uq_availability_tenant_agenda"),
                Session(bind=engine) as session,
            ):
                clinic.uow(session).availability.save(build_weekday_availability(
                    clinic.tenant.id, None, agenda_id=agenda.id
                ))
                session.commit()
            with (
                pytest.raises(IntegrityError, match="ck_availability_one_assignee"),
                Session(bind=engine) as session,
            ):
                session.execute(text(
                    "INSERT INTO doctor_availability (id, tenant_id, weekly, rules) "
                    "VALUES (:id, :t, '[]', '{}')"
                ), {"id": uuid.uuid4(), "t": clinic.tenant.id.value})
                session.commit()

    def test_a_doctor_and_an_agenda_schedule_coexist(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            _agenda(clinic)
            with Session(bind=engine) as session:
                clinic.uow(session).availability.save(
                    build_weekday_availability(clinic.tenant.id, clinic.doctor.id)
                )
                session.commit()

            assert _scalar(clinic, "SELECT count(*) FROM doctor_availability "
                                   "WHERE tenant_id = :t") == 2

    def test_the_agenda_name_is_unique_per_clinic_whatever_its_case(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            _agenda(clinic, "Vacunatorio")

            with pytest.raises(ConflictError) as error:
                _agenda(clinic, "VACUNATORIO")
            assert error.value.code == "service_agenda.name_taken"
            assert error.value.params == {"name": "VACUNATORIO"}

            with Session(bind=engine) as session:
                repo = clinic.uow(session).service_agendas
                assert repo.name_exists("vacunatorio")
                assert not repo.name_exists("Otra")


class TestConcurrency:
    def test_two_bookings_of_one_agenda_slot_create_one(self, engine):  # noqa: F811
        with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
            agenda = _agenda(clinic)
            holder = Session(bind=engine)
            try:
                clinic.uow(holder).appointments.lock_bookings(Assignee.agenda(agenda.id))
                futures = [pool.submit(_book, clinic, agenda) for _ in range(2)]
                for future in futures:
                    with pytest.raises(FutureTimeout):
                        future.result(timeout=WAIT)
                holder.rollback()
            finally:
                holder.close()

            assert sorted(_outcome(f) for f in futures) == ["done", "slot.not_bookable"]
            assert _scalar(clinic, "SELECT count(*) FROM appointments WHERE tenant_id = :t "
                                   "AND agenda_id = :a", a=agenda.id.value) == 1

    def test_the_agenda_lock_does_not_hold_back_a_doctor(self, engine):  # noqa: F811
        with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=1) as pool:
            agenda = _agenda(clinic)
            with Session(bind=engine) as session:
                clinic.uow(session).availability.save(
                    build_weekday_availability(clinic.tenant.id, clinic.doctor.id)
                )
                session.commit()
            holder = Session(bind=engine)
            try:
                clinic.uow(holder).appointments.lock_bookings(Assignee.agenda(agenda.id))

                def doctor_booking() -> None:
                    with Session(bind=engine, expire_on_commit=False) as session:
                        uow = clinic.uow(session)
                        CreateAppointment(
                            uow, uow.code_generator(), FixedClock(BOOKING_CLOCK)
                        ).execute(_staff(clinic), CreateAppointmentCommand(
                            patient_id=clinic.patient.id, doctor_id=clinic.doctor.id,
                            location_id=clinic.tenant.primary_location.id,
                            type=AppointmentType.CONSULT, scheduled_start=SLOT, reason="x",
                        ))

                pool.submit(doctor_booking).result(timeout=5)
                holder.rollback()
            finally:
                holder.close()

            assert _scalar(clinic, "SELECT count(*) FROM appointments WHERE tenant_id = :t "
                                   "AND doctor_id IS NOT NULL AND scheduled_start = :s",
                           s=SLOT) == 1

    def test_two_registrations_of_one_visit_record_the_doses_once(self, engine):  # noqa: F811
        with Clinic(engine) as clinic, ThreadPoolExecutor(max_workers=2) as pool:
            agenda = _agenda(clinic)
            appointment = _vaccination_appointment(clinic, agenda)
            holder = Session(bind=engine)
            try:
                clinic.uow(holder).appointments.get_for_update(appointment.id)
                futures = [pool.submit(_visit, clinic, appointment) for _ in range(2)]
                for future in futures:
                    with pytest.raises(FutureTimeout):
                        future.result(timeout=WAIT)
                holder.rollback()
            finally:
                holder.close()

            assert sorted(_outcome(f) for f in futures) == [
                "done", "vaccination.appointment_mismatch"
            ]
            assert _scalar(clinic, "SELECT count(*) FROM vaccination_records "
                                   "WHERE tenant_id = :t AND appointment_id = :a",
                           a=appointment.id.value) == 1
            assert _scalar(clinic, "SELECT status FROM appointments WHERE id = :a",
                           a=appointment.id.value) == "completed"
            assert _scalar(clinic, "SELECT occurred_on FROM vaccination_records "
                                   "WHERE tenant_id = :t") == date(2026, 6, 1)


def _raw_appointment(clinic: Clinic, patient_id, agenda_id=None) -> dict:
    return {
        "id": uuid.uuid4(), "t": clinic.tenant.id.value, "p": patient_id,
        "d": None if agenda_id else clinic.doctor.id.value, "a": agenda_id,
        "l": clinic.tenant.primary_location.id.value, "c": clinic.doctor.id.value,
    }


_INSERT_APPOINTMENT = text(
    "INSERT INTO appointments (id, tenant_id, code, patient_id, doctor_id, agenda_id, "
    "location_id, type, status, scheduled_start, duration_minutes, reason, created_by_id) "
    "VALUES (:id, :t, 'A-X', :p, :d, :a, :l, 'vaccination', 'scheduled', "
    "'2026-06-01 09:00', 15, 'x', :c)"
)


class TestTenantIsolation:
    def test_an_appointment_cannot_point_at_another_clinics_agenda(self, engine):  # noqa: F811
        with Clinic(engine) as mine, Clinic(engine) as theirs:
            foreign = _agenda(theirs)

            with (
                pytest.raises(IntegrityError, match="fk_appointments_tenant_agenda"),
                Session(bind=engine) as session,
            ):
                session.execute(
                    _INSERT_APPOINTMENT,
                    _raw_appointment(mine, mine.patient.id.value, foreign.id.value),
                )
                session.commit()

    def test_a_dose_cannot_point_at_another_clinics_appointment(self, engine):  # noqa: F811
        with Clinic(engine) as mine, Clinic(engine) as theirs:  # noqa: SIM117
            with (
                pytest.raises(IntegrityError, match="fk_vaccination_records_tenant_appointment"),
                Session(bind=engine) as session,
            ):
                session.execute(text(
                    "INSERT INTO vaccination_records (id, tenant_id, patient_id, "
                    "appointment_id, vaccine_code, outcome, occurred_on, source, "
                    "recorded_by_id) VALUES (:id, :t, :p, :a, 'TD', 'administered', "
                    "'2026-06-01', 'clinic', :c)"
                ), {"id": uuid.uuid4(), "t": mine.tenant.id.value,
                    "p": mine.patient.id.value, "a": theirs.appointment.id.value,
                    "c": mine.doctor.id.value})
                session.commit()

    def test_a_schedule_cannot_point_at_another_clinics_agenda(self, engine):  # noqa: F811
        with Clinic(engine) as mine, Clinic(engine) as theirs:
            foreign = _agenda(theirs)

            with (
                pytest.raises(IntegrityError, match="fk_availability_tenant_agenda"),
                Session(bind=engine) as session,
            ):
                session.execute(text(
                    "INSERT INTO doctor_availability (id, tenant_id, agenda_id, weekly, rules) "
                    "VALUES (:id, :t, :a, '[]', '{}')"
                ), {"id": uuid.uuid4(), "t": mine.tenant.id.value, "a": foreign.id.value})
                session.commit()

    def test_an_agenda_cannot_use_another_clinics_location(self, engine):  # noqa: F811
        with Clinic(engine) as mine, Clinic(engine) as theirs:  # noqa: SIM117
            with (
                pytest.raises(IntegrityError, match="fk_service_agendas_tenant_location"),
                Session(bind=engine) as session,
            ):
                session.execute(text(
                    "INSERT INTO service_agendas (id, tenant_id, name, kind, location_id) "
                    "VALUES (:id, :t, 'X', 'vaccination', :l)"
                ), {"id": uuid.uuid4(), "t": mine.tenant.id.value,
                    "l": theirs.tenant.primary_location.id.value})
                session.commit()

    def test_reports_do_not_join_another_clinics_patient(self, engine):  # noqa: F811
        with Clinic(engine) as mine, Clinic(engine) as theirs:
            # Appointments carry no tenant check on the patient, so the join must.
            stray = _raw_appointment(mine, theirs.patient.id.value)
            with Session(bind=engine) as session:
                session.execute(_INSERT_APPOINTMENT, stray)
                session.commit()
            try:
                with Session(bind=engine) as session:
                    rows = clinic_rows(mine, session)
                assert [r.code for r in rows] == ["A-1"]  # only the clinic's own appointment
            finally:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM appointments WHERE id = :id"),
                                 {"id": stray["id"]})


def clinic_rows(clinic: Clinic, session: Session):
    return clinic.uow(session).reports.appointment_rows(
        datetime(2026, 6, 1), datetime(2026, 6, 2)
    )


class TestLockKey:
    def test_the_doctor_lock_is_the_one_the_previous_release_took(self, engine):  # noqa: F811
        # Old and new containers run side by side during a deploy: they must collide.
        with Clinic(engine) as clinic:
            digest = hashlib.sha256(
                f"doctor_bookings:{clinic.tenant.id.value}:{clinic.doctor.id.value}".encode()
            ).digest()
            old_key = int.from_bytes(digest[:8], "big", signed=True)
            holder = Session(bind=engine)
            try:
                holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": old_key})
                with Session(bind=engine) as session:
                    session.execute(text("SET LOCAL lock_timeout = '300ms'"))
                    with pytest.raises(OperationalError, match="LockNotAvailable"):
                        clinic.uow(session).appointments.lock_bookings(
                            Assignee.doctor(clinic.doctor.id)
                        )
            finally:
                holder.rollback()
                holder.close()


class TestVisitDuplicates:
    def test_the_same_one_off_dose_twice_in_a_visit_saves_nothing(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            agenda = _agenda(clinic)
            appointment = _vaccination_appointment(clinic, agenda)
            dose = VisitDose("HEXA", lot="L-1", dose_key="HEXA-1")

            with (
                Session(bind=engine, expire_on_commit=False) as session,
                pytest.raises(ValidationError) as error,
            ):
                RecordVaccinationVisit(clinic.uow(session), FixedClock(TODAY_CLOCK)).execute(
                    _staff(clinic, Role.NURSE),
                    RecordVaccinationVisitCommand(
                        appointment_id=appointment.id, patient_id=clinic.patient.id,
                        doses=(dose, dose),
                    ),
                )

            assert error.value.code == "vaccination.dose_already_recorded"
            assert _scalar(clinic, "SELECT count(*) FROM vaccination_records "
                                   "WHERE tenant_id = :t") == 0
            assert _scalar(clinic, "SELECT status FROM appointments WHERE id = :a",
                           a=appointment.id.value) == "confirmed"

    def test_only_todays_appointment_can_be_closed(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            agenda = _agenda(clinic)
            appointment = _vaccination_appointment(clinic, agenda)

            with (
                Session(bind=engine, expire_on_commit=False) as session,
                pytest.raises(ValidationError) as error,
            ):
                RecordVaccinationVisit(
                    clinic.uow(session), FixedClock(datetime(2026, 6, 2, 9, 0, tzinfo=UTC))
                ).execute(
                    _staff(clinic, Role.NURSE),
                    RecordVaccinationVisitCommand(
                        appointment_id=appointment.id, patient_id=clinic.patient.id,
                        doses=(VisitDose("TD", lot="L-1"),),
                    ),
                )

            assert error.value.code == "vaccination.appointment_not_today"


class TestAgendaSchedules:
    def test_schedules_of_many_agendas_come_in_one_call(self, engine):  # noqa: F811
        with Clinic(engine) as clinic:
            first, second = _agenda(clinic, "Uno"), _agenda(clinic, "Dos")

            with Session(bind=engine) as session:
                found = clinic.uow(session).availability.list_for_agendas(
                    [first.id, second.id]
                )

            assert set(found) == {first.id, second.id}
            assert all(a.rules.slot_minutes == 15 for a in found.values())
