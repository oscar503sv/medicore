"""Seed rich demo data that reflects the current system.

Per tenant: 1 admin, 5 doctors (with availability), 1 nurse, 1 receptionist, 30 patients,
4 insurers — plus realistic activity so the app looks populated:

* Past (~8 weeks → today): weekly signed consultations per doctor → MedicalRecords with
  vitals, diagnoses and prescriptions (insurer frozen on the record), and matching audit.
* Future (today → end of October 2026): weekly scheduled/confirmed appointments → agenda
  and "next appointment".
* Audit entries (logins, patient.created, appointment.created, consultation.signed,
  record.viewed) carry a human ``subject`` so the audit Detail column is meaningful.

Idempotent: re-running skips tenants/users/patients that already exist and skips activity if
the tenant already has appointments. Use ``--reset`` to wipe the demo tenants first (cascade).

Usage:
    .venv/bin/python scripts/seed_demo.py [--reset]
"""

from __future__ import annotations

import argparse
import random
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.availability import BookingRules, DoctorAvailability, WeeklyDay
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.prescription import Prescription, PrescriptionSnapshot
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import (
    AppointmentStatus,
    AppointmentType,
    ClinicalRecordType,
    PatientStatus,
    PrescriptionStatus,
    Role,
    Sex,
    UserStatus,
)
from medicore.domain.shared.identifiers import (
    AppointmentId,
    AvailabilityId,
    InsurerId,
    LocationId,
    PatientId,
    PrescriptionId,
    RecordId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.time_range import TimeRange
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from medicore.infrastructure.auth.code_generator import DbSequentialCodeGenerator
from medicore.infrastructure.database.engine import get_session
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

PASSWORD = "demo1234"
HASHER = BcryptPasswordHasher()
RNG = random.Random(42)

LAST_NAMES = [
    "García", "Fernández", "González", "Rodríguez", "López", "Martínez", "Sánchez",
    "Pérez", "Gómez", "Ruiz", "Díaz", "Moreno", "Álvarez", "Romero", "Torres",
]
FEMALE_NAMES = ["María", "Carmen", "Ana", "Laura", "Lucía", "Elena", "Sofía", "Marta", "Paula", "Rosa"]
MALE_NAMES = ["Juan", "Carlos", "Miguel", "Antonio", "Javier", "David", "Pablo", "Sergio", "Hugo", "Diego"]
BLOOD = ["O+", "A+", "B+", "O-", "A-", "AB+"]
TAGS = [["Hipertensión"], ["Diabetes tipo 2"], ["Asma"], [], ["Hipotiroidismo"], ["Migraña"]]
ALLERGIES = [["Penicilina"], [], ["Polen"], ["Frutos secos"], [], ["AINE"]]

INSURERS = [
    ("Sanitas", "900100100", "atencion@sanitas.test", "Calle Ribera del Loira 52, Madrid"),
    ("Adeslas", "900200200", "clientes@adeslas.test", "Paseo de la Castellana 259, Madrid"),
    ("DKV Seguros", "900300300", "info@dkv.test", "Av. María Zambrano 31, Zaragoza"),
    ("Mapfre Salud", "900400400", "salud@mapfre.test", "Ctra. de Pozuelo 52, Majadahonda"),
]

DIAGNOSES = [
    ("I10", "Hipertensión esencial"),
    ("E11.9", "Diabetes mellitus tipo 2"),
    ("J45.909", "Asma no especificada"),
    ("M54.5", "Lumbalgia"),
    ("J06.9", "Infección respiratoria aguda"),
    ("K21.9", "Reflujo gastroesofágico"),
    ("N39.0", "Infección de vías urinarias"),
    ("F41.1", "Trastorno de ansiedad generalizada"),
]
MEDS = [
    ("Enalapril", "20 mg", "1× día · mañana", 30),
    ("Metformina", "850 mg", "2× día", 90),
    ("Salbutamol", "100 mcg", "2 inhalaciones c/8h", 30),
    ("Ibuprofeno", "400 mg", "c/8h", 7),
    ("Amoxicilina", "500 mg", "c/8h", 10),
    ("Omeprazol", "20 mg", "1× día · ayunas", 28),
    ("Loratadina", "10 mg", "1× día", 15),
]
REASONS = [
    "Control de hipertensión", "Dolor abdominal", "Revisión general", "Seguimiento diabetes",
    "Cefalea persistente", "Dolor lumbar", "Tos y fiebre", "Chequeo anual", "Reacción alérgica",
    "Control de tiroides",
]
WORK_HOURS = [9, 10, 11, 12, 13, 16, 17, 18]

# Per-tenant staff: (name, email_local, role, specialty). Admin is added separately.
STAFF = {
    "clinica-demo": [
        ("Dra. Elena Ruiz", "elena.ruiz", Role.DOCTOR, "Cardiología"),
        ("Dr. Marco Vidal", "marco.vidal", Role.DOCTOR, "Medicina General"),
        ("Dra. Paula Méndez", "paula.mendez", Role.DOCTOR, "Pediatría"),
        ("Dr. Andrés Soto", "andres.soto", Role.DOCTOR, "Dermatología"),
        ("Dra. Carla Núñez", "carla.nunez", Role.DOCTOR, "Ginecología"),
        ("Lucía Méndez", "lucia.mendez", Role.NURSE, "Enfermería"),
        ("Sara Gil", "sara.gil", Role.RECEPTIONIST, None),
    ],
    "centro-norte": [
        ("Dra. Núria Soler", "nuria.soler", Role.DOCTOR, "Pediatría"),
        ("Dr. Iván Costa", "ivan.costa", Role.DOCTOR, "Traumatología"),
        ("Dr. Pol Ferrer", "pol.ferrer", Role.DOCTOR, "Medicina General"),
        ("Dra. Aina Vidal", "aina.vidal", Role.DOCTOR, "Endocrinología"),
        ("Dr. Marc Roig", "marc.roig", Role.DOCTOR, "Cardiología"),
        ("Marta Roca", "marta.roca", Role.NURSE, "Enfermería"),
        ("Jordi Pla", "jordi.pla", Role.RECEPTIONIST, None),
    ],
}


# ── builders ────────────────────────────────────────────────────────────────
def weekday_availability(tid: TenantId, doctor_id: UserId) -> DoctorAvailability:
    """Mon–Fri 09:00–14:00 + 16:00–19:00."""
    weekly = [
        WeeklyDay(
            day_of_week=d,
            enabled=d < 5,
            blocks=[TimeRange(time(9, 0), time(14, 0)), TimeRange(time(16, 0), time(19, 0))]
            if d < 5
            else [],
        )
        for d in range(7)
    ]
    return DoctorAvailability(
        id=AvailabilityId.new(),
        tenant_id=tid,
        doctor_id=doctor_id,
        weekly=weekly,
        rules=BookingRules(slot_minutes=30, buffer_minutes=0, max_advance_days=365),
    )


def make_user(tid: TenantId, name: str, email: str, role: Role, specialty=None) -> User:
    first = name.replace("Dr. ", "").replace("Dra. ", "").split()[0]
    sex = Sex.FEMALE if first.lower().endswith("a") else Sex.MALE
    return User(
        id=UserId.new(),
        tenant_id=tid,
        name=name,
        email=email,
        password_hash=HASHER.hash(PASSWORD),
        role=role,
        status=UserStatus.ACTIVE,
        sex=sex,
        specialty=specialty,
    )


def make_patient(tid: TenantId, code: str, i: int, doctor_id: UserId) -> Patient:
    is_female = i % 2 == 0
    first = (FEMALE_NAMES if is_female else MALE_NAMES)[i % 10]
    last = f"{LAST_NAMES[i % len(LAST_NAMES)]} {LAST_NAMES[(i + 5) % len(LAST_NAMES)]}"
    year = 1955 + (i * 37) % 50
    month = 1 + (i * 7) % 12
    day = 1 + (i * 13) % 28
    return Patient(
        id=PatientId.new(),
        tenant_id=tid,
        code=code,
        first_name=first,
        last_name=last,
        sex=Sex.FEMALE if is_female else Sex.MALE,
        date_of_birth=date(year, month, day),
        blood_type=BloodType(BLOOD[i % len(BLOOD)]),
        primary_doctor_id=doctor_id,
        status=PatientStatus.ACTIVE,
        tags=list(TAGS[i % len(TAGS)]),
        allergies=list(ALLERGIES[i % len(ALLERGIES)]),
        contact=ContactInfo(
            phone=f"7{RNG.randint(100, 999)}-{RNG.randint(1000, 9999)}",
            email=f"{first.lower()}.{i}@example.com",
            address=f"Calle {LAST_NAMES[i % len(LAST_NAMES)]} {10 + i}, Col. Centro",
            emergency_contact_name=f"{MALE_NAMES[i % 10]} {last.split()[0]}",
            emergency_contact_phone=f"7{RNG.randint(100, 999)}-{RNG.randint(1000, 9999)}",
        ),
    )


def make_vitals() -> Vitals:
    sys, dia = RNG.randint(108, 148), RNG.randint(68, 96)
    return Vitals(
        blood_pressure=f"{sys}/{dia}",
        heart_rate=RNG.randint(58, 96),
        spo2=RNG.randint(95, 100),
        temperature=Decimal(f"{RNG.randint(360, 378) / 10:.1f}"),
        weight=Decimal(f"{RNG.randint(550, 980) / 10:.1f}"),
        glucose=RNG.randint(78, 145),
        height=Decimal(RNG.randint(150, 190)),
    )


def ctx(tid: TenantId, user: User) -> ActorContext:
    return ActorContext(
        user_id=user.id, tenant_id=tid, role=user.role, ip_address="127.0.0.1",
        user_agent="seed-demo/1.0",
    )


def mondays(start: date, end: date):
    """Yield the Monday of each week from ``start``'s week through ``end``."""
    d = start - timedelta(days=start.weekday())
    while d <= end:
        yield d
        d += timedelta(weeks=1)


# ── tenant seeding ────────────────────────────────────────────────────────────
def get_or_create_tenant(session, slug: str, legal_name: str, location_name: str) -> Tenant:
    row = session.query(TenantModel).filter(TenantModel.slug == slug).first()
    if row:
        print(f"  tenant '{slug}' ya existe")
        tid = TenantId.parse(row.id)
        return SqlAlchemyUnitOfWork(session, tid).tenants.get_by_id(tid)
    tid = TenantId.new()
    tenant = Tenant(
        id=tid,
        legal_name=legal_name,
        tax_id="B00000000",
        slug=Slug(slug),
        timezone="America/El_Salvador",
        locations=[Location(id=LocationId.new(), tenant_id=tid, name=location_name, is_primary=True)],
    )
    uow = SqlAlchemyUnitOfWork(session, tid)
    with uow:
        uow.tenants.save(tenant)
        uow.commit()
    print(f"  tenant '{slug}' creado")
    return tenant


def seed_staff(session, tenant: Tenant) -> tuple[User, list[User], User, User]:
    """Create admin + staff; return (admin, doctors, nurse, receptionist)."""
    tid = tenant.id
    uow = SqlAlchemyUnitOfWork(session, tid)
    doctors: list[User] = []
    nurse: User | None = None
    receptionist: User | None = None
    with uow:
        admin_email = f"admin@{tenant.slug}.test"
        admin = uow.users.get_by_email(admin_email) or make_user(tid, "Admin Demo", admin_email, Role.ADMIN)
        if uow.users.get_by_email(admin_email) is None:
            uow.users.save(admin)

        for name, local, role, specialty in STAFF[str(tenant.slug)]:
            email = f"{local}@{tenant.slug}.test"
            existing = uow.users.get_by_email(email)
            user = existing or make_user(tid, name, email, role, specialty)
            if existing is None:
                uow.users.save(user)
                if role == Role.DOCTOR:
                    uow.availability.save(weekday_availability(tid, user.id))
            if role == Role.DOCTOR:
                doctors.append(user)
            elif role == Role.NURSE:
                nurse = user
            elif role == Role.RECEPTIONIST:
                receptionist = user
        uow.commit()
    print(f"    + staff: admin, {len(doctors)} doctores, enfermera, recepción")
    return admin, doctors, nurse, receptionist


def seed_insurers(session, tid: TenantId) -> list[InsurerId | None]:
    uow = SqlAlchemyUnitOfWork(session, tid)
    ids: list[InsurerId | None] = []
    with uow:
        existing = {ins.name: ins.id for ins in uow.insurers.list()}
        for name, phone, email, address in INSURERS:
            if name in existing:
                ids.append(existing[name])
                continue
            ins = Insurer(id=InsurerId.new(), tenant_id=tid, name=name, phone=phone, email=email, address=address)
            uow.insurers.save(ins)
            ids.append(ins.id)
        uow.commit()
    ids.append(None)  # some patients are private
    return ids


def seed_patients(session, tid: TenantId, doctors: list[User], insurer_ids) -> list[Patient]:
    uow = SqlAlchemyUnitOfWork(session, tid)
    codes = DbSequentialCodeGenerator(session, tid.value)
    existing = uow.patients.list()
    if existing.total >= 30:
        print(f"    pacientes: ya hay {existing.total}, omitido")
        return uow.patients.list().items
    patients: list[Patient] = []
    with uow:
        for i in range(30):
            p = make_patient(tid, codes.next_patient_code(), i, doctors[i % len(doctors)].id)
            uow.patients.save(p)
            patients.append(p)
        uow.commit()
    print("    + 30 pacientes")
    return patients


def seed_activity(
    session,
    tid: TenantId,
    admin: User,
    doctors: list[User],
    reception: User,
    patients: list[Patient],
    insurer_ids,
    today: date,
) -> None:
    if session.query(AppointmentModel).filter(AppointmentModel.tenant_id == tid.value).first():
        print("    actividad: el tenant ya tiene citas, omitido")
        return

    uow = SqlAlchemyUnitOfWork(session, tid)
    codes = DbSequentialCodeGenerator(session, tid.value)
    reader = SqlAlchemyUnitOfWork(session, tid)
    location_id = reader.tenants.get_by_id(tid).locations[0].id
    insurer_names = {ins.id: ins.name for ins in reader.insurers.list()}

    n_past = n_future = 0
    with uow:
        # Account creation + login audit, spread before the activity window.
        base = datetime.now(UTC) - timedelta(days=63)
        for n, p in enumerate(patients):
            uow.audit.append(
                audit_entry(
                    ctx(tid, reception), base + timedelta(hours=n), "patient.created", "Patient",
                    str(p.id), subject=subject(p.code, p.full_name),
                )
            )
        for n, u in enumerate([admin, reception, *doctors]):
            uow.audit.append(
                audit_entry(
                    ctx(tid, u), datetime.now(UTC) - timedelta(days=RNG.randint(0, 5), hours=n),
                    "auth.login", "User", str(u.id),
                )
            )

        # Past: signed consultations (records + prescriptions + audit).
        for monday in mondays(today - timedelta(weeks=8), today - timedelta(days=1)):
            for doc in doctors:
                for _ in range(RNG.randint(2, 3)):
                    day = monday + timedelta(days=RNG.randint(0, 4))
                    if day >= today:
                        continue
                    start = datetime.combine(day, time(RNG.choice(WORK_HOURS), 0))
                    encounter = start.replace(tzinfo=UTC)
                    patient = RNG.choice(patients)
                    insurer_id = patient_insurer(patient, insurer_ids)
                    appt = Appointment(
                        id=AppointmentId.new(), tenant_id=tid, code=codes.next_appointment_code(),
                        patient_id=patient.id, doctor_id=doc.id, location_id=location_id,
                        type=AppointmentType.CONSULT, scheduled_start=start, duration_minutes=30,
                        reason=RNG.choice(REASONS), created_by_id=reception.id,
                        status=AppointmentStatus.COMPLETED, insurance_id=insurer_id,
                        created_at=encounter - timedelta(days=3), updated_at=encounter,
                    )
                    uow.appointments.save(appt)

                    dx = [IcdCode(*RNG.choice(DIAGNOSES))]
                    snaps, scripts = build_prescriptions(tid, patient, doc, day, today)
                    record = MedicalRecord(
                        id=RecordId.new(), tenant_id=tid,
                        code=codes.next_record_code(ClinicalRecordType.CONSULTATION, day),
                        patient_id=patient.id, author_id=doc.id,
                        type=ClinicalRecordType.CONSULTATION, encounter_at=encounter,
                        location_name="Sede principal", insurer_name=insurer_names.get(insurer_id),
                        chief_complaint=appt.reason, soap=make_soap(appt.reason), vitals=make_vitals(),
                        signed_at=encounter, signed_by_id=doc.id, appointment_id=appt.id,
                        diagnoses=tuple(dx), prescriptions=tuple(snaps),
                    )
                    uow.medical_records.save(record)
                    for rx in scripts:
                        uow.prescriptions.save(rx)
                    uow.audit.append(
                        audit_entry(
                            ctx(tid, reception), encounter - timedelta(days=3),
                            "appointment.created", "Appointment", str(appt.id),
                            subject=subject(appt.code, patient.full_name),
                        )
                    )
                    uow.audit.append(
                        audit_entry(
                            ctx(tid, doc), encounter, "consultation.signed", "MedicalRecord",
                            str(record.id), prescriptions=len(scripts),
                            subject=subject(record.code, patient.full_name),
                        )
                    )
                    uow.audit.append(
                        audit_entry(
                            ctx(tid, doc), encounter + timedelta(minutes=RNG.randint(5, 90)),
                            "record.viewed", "MedicalRecord", str(record.id),
                            subject=subject(record.code, patient.full_name),
                        )
                    )
                    n_past += 1

        # Future: scheduled/confirmed appointments (agenda + next visit).
        end = date(today.year, 10, 31)
        for monday in mondays(today + timedelta(days=1), end):
            for doc in doctors:
                for k in range(2):
                    day = monday + timedelta(days=RNG.randint(0, 4))
                    if day <= today or day > end:
                        continue
                    start = datetime.combine(day, time(RNG.choice(WORK_HOURS), 0))
                    patient = RNG.choice(patients)
                    insurer_id = patient_insurer(patient, insurer_ids)
                    appt = Appointment(
                        id=AppointmentId.new(), tenant_id=tid, code=codes.next_appointment_code(),
                        patient_id=patient.id, doctor_id=doc.id, location_id=location_id,
                        type=AppointmentType.CONSULT, scheduled_start=start, duration_minutes=30,
                        reason=RNG.choice(REASONS), created_by_id=reception.id,
                        status=AppointmentStatus.CONFIRMED if k == 0 else AppointmentStatus.SCHEDULED,
                        insurance_id=insurer_id,
                    )
                    uow.appointments.save(appt)
                    uow.audit.append(
                        audit_entry(
                            ctx(tid, reception),
                            datetime.now(UTC) - timedelta(days=RNG.randint(0, 7)),
                            "appointment.created", "Appointment", str(appt.id),
                            subject=subject(appt.code, patient.full_name),
                        )
                    )
                    n_future += 1
        uow.commit()
    print(f"    + actividad: {n_past} consultas firmadas, {n_future} citas futuras")


def patient_insurer(patient: Patient, insurer_ids):
    """Deterministic insurer per patient (every 4th is private)."""
    h = int(patient.code.split("-")[-1]) if "-" in patient.code else 0
    return None if h % 4 == 0 else insurer_ids[h % (len(insurer_ids) - 1)]


def build_prescriptions(tid, patient, doctor, day, today):
    """Return (snapshots for the record, Prescription aggregates) for ~0–2 meds."""
    snaps: list[PrescriptionSnapshot] = []
    scripts: list[Prescription] = []
    for drug, dose, sched, dur in RNG.sample(MEDS, RNG.randint(0, 2)):
        end = day + timedelta(days=dur)
        snaps.append(PrescriptionSnapshot(drug=drug, dose=dose, schedule=sched, start_date=day, end_date=end, duration_days=dur))
        scripts.append(
            Prescription(
                id=PrescriptionId.new(), tenant_id=tid, patient_id=patient.id, prescriber_id=doctor.id,
                drug=drug, dose=dose, schedule=sched, start_date=day, end_date=end, duration_days=dur,
                status=PrescriptionStatus.ACTIVE if end >= today else PrescriptionStatus.COMPLETED,
            )
        )
    return snaps, scripts


def make_soap(reason: str) -> SoapNote:
    return SoapNote(
        subjective=f"Paciente refiere {reason.lower()}.",
        objective="Constantes dentro de parámetros. Exploración sin hallazgos relevantes.",
        assessment="Cuadro compatible con el motivo de consulta; evolución favorable.",
        plan="Tratamiento indicado, medidas higiénico-dietéticas y control evolutivo.",
    )


def seed_tenant(session, slug: str, legal_name: str, location_name: str, today: date) -> None:
    print(f"Tenant: {slug}")
    tenant = get_or_create_tenant(session, slug, legal_name, location_name)
    admin, doctors, _nurse, reception = seed_staff(session, tenant)
    insurer_ids = seed_insurers(session, tenant.id)
    patients = seed_patients(session, tenant.id, doctors, insurer_ids)
    seed_activity(session, tenant.id, admin, doctors, reception, patients, insurer_ids, today)


def reset_demo(session, slugs: list[str]) -> None:
    session.execute(delete(TenantModel).where(TenantModel.slug.in_(slugs)))
    session.commit()
    print(f"Reset: tenants {slugs} borrados (cascada)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="borra los tenants demo antes de sembrar")
    args = parser.parse_args()

    session = get_session()
    today = date.today()
    demo = [("clinica-demo", "Clínica Demo SL", "San Salvador · Centro"),
            ("centro-norte", "Centro Médico Norte SL", "Santa Tecla · Las Palmas")]

    if args.reset:
        reset_demo(session, [s for s, _, _ in demo])

    for slug, legal_name, location_name in demo:
        seed_tenant(session, slug, legal_name, location_name, today)

    session.close()
    print("\nListo. Contraseña de todos los usuarios demo:", PASSWORD)


if __name__ == "__main__":
    main()
