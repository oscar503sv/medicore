"""Seed rich demo data: staff (doctors/nurses/receptionists), a second tenant,
and 15 patients per tenant.

Idempotent: re-running it skips tenants/users/patients that already exist.

Usage:
    .venv/bin/python scripts/seed_demo.py
"""

from __future__ import annotations

from datetime import date, time

from medicore.domain.entities.availability import (
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import PatientStatus, Role, Sex, UserStatus
from medicore.domain.shared.identifiers import (
    AvailabilityId,
    InsurerId,
    LocationId,
    PatientId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.time_range import TimeRange
from medicore.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from medicore.infrastructure.auth.code_generator import DbSequentialCodeGenerator
from medicore.infrastructure.database.engine import get_session
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

PASSWORD = "demo1234"
HASHER = BcryptPasswordHasher()

FEMALE_NAMES = ["María", "Carmen", "Ana", "Laura", "Lucía", "Elena", "Sofía", "Marta"]
MALE_NAMES = ["Juan", "Carlos", "Miguel", "Antonio", "Javier", "David", "Pablo", "Sergio"]
LAST_NAMES = [
    "García", "Fernández", "González", "Rodríguez", "López", "Martínez", "Sánchez",
    "Pérez", "Gómez", "Ruiz", "Díaz", "Moreno", "Álvarez", "Romero", "Torres",
]
BLOOD = ["O+", "A+", "B+", "O-", "A-", "AB+"]
TAGS = [["Hipertensión"], ["Diabetes tipo 2"], ["Asma"], [], ["Hipotiroidismo"], ["Migraña"]]
ALLERGIES = [["Penicilina"], [], ["Polen"], ["Frutos secos"], [], ["AINE"]]
# (name, phone, email, address) — demo insurers seeded per tenant.
INSURERS = [
    ("Sanitas", "900100100", "atencion@sanitas.test", "Calle Ribera del Loira 52, Madrid"),
    ("Adeslas", "900200200", "clientes@adeslas.test", "Paseo de la Castellana 259, Madrid"),
    ("DKV Seguros", "900300300", "info@dkv.test", "Av. María Zambrano 31, Zaragoza"),
    ("Mapfre Salud", "900400400", "salud@mapfre.test", "Ctra. de Pozuelo 52, Majadahonda"),
]


def weekday_availability(tenant_id: TenantId, doctor_id: UserId) -> DoctorAvailability:
    """Mon–Fri 09:00–14:00 + 16:00–19:00."""
    weekly = []
    for d in range(7):
        if d < 5:
            weekly.append(
                WeeklyDay(
                    day_of_week=d,
                    enabled=True,
                    blocks=[
                        TimeRange(time(9, 0), time(14, 0)),
                        TimeRange(time(16, 0), time(19, 0)),
                    ],
                )
            )
        else:
            weekly.append(WeeklyDay(day_of_week=d, enabled=False, blocks=[]))
    return DoctorAvailability(
        id=AvailabilityId.new(),
        tenant_id=tenant_id,
        doctor_id=doctor_id,
        weekly=weekly,
        rules=BookingRules(slot_minutes=30, buffer_minutes=0, max_advance_days=365),
    )


def make_user(tenant_id, name, email, role, specialty=None) -> User:
    # Demo heuristic: Spanish given names ending in "a" are typically female.
    first = name.split()[0]
    sex = Sex.FEMALE if first.lower().endswith("a") else Sex.MALE
    return User(
        id=UserId.new(),
        tenant_id=tenant_id,
        name=name,
        email=email,
        password_hash=HASHER.hash(PASSWORD),
        role=role,
        status=UserStatus.ACTIVE,
        sex=sex,
        specialty=specialty,
    )


def make_patient(tenant_id, code, i, doctor_id) -> Patient:
    is_female = i % 2 == 0
    first = (FEMALE_NAMES if is_female else MALE_NAMES)[i % 8]
    last = f"{LAST_NAMES[i % len(LAST_NAMES)]} {LAST_NAMES[(i + 5) % len(LAST_NAMES)]}"
    year = 1955 + (i * 37) % 50
    month = 1 + (i * 7) % 12
    day = 1 + (i * 13) % 28
    return Patient(
        id=PatientId.new(),
        tenant_id=tenant_id,
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
            phone=f"6{10000000 + i * 13579:08d}",
            email=f"{first.lower()}.{i}@example.com",
        ),
    )


def get_or_create_tenant(session, slug: str, legal_name: str, location_name: str) -> Tenant:
    row = session.query(TenantModel).filter(TenantModel.slug == slug).first()
    if row:
        print(f"  tenant '{slug}' ya existe")
        tid = TenantId.parse(row.id)
        uow = SqlAlchemyUnitOfWork(session, tid)
        return uow.tenants.get_by_id(tid)
    tid = TenantId.new()
    tenant = Tenant(
        id=tid,
        legal_name=legal_name,
        tax_id="B00000000",
        slug=Slug(slug),
        timezone="America/El_Salvador",
        locations=[
            Location(id=LocationId.new(), tenant_id=tid, name=location_name, is_primary=True)
        ],
    )
    uow = SqlAlchemyUnitOfWork(session, tid)
    with uow:
        uow.tenants.save(tenant)
        uow.commit()
    print(f"  tenant '{slug}' creado")
    return tenant


def seed_tenant(session, tenant: Tenant, staff: list[tuple], add_admin: bool) -> None:
    tid = tenant.id
    uow = SqlAlchemyUnitOfWork(session, tid)
    codes = DbSequentialCodeGenerator(session, tid.value)

    doctors: list[UserId] = []
    with uow:
        if add_admin:
            email = f"admin@{tenant.slug}.test"
            if not uow.users.get_by_email(email):
                uow.users.save(make_user(tid, "Admin Demo", email, Role.ADMIN))
                print(f"    + admin {email}")

        for name, email, role, specialty in staff:
            if uow.users.get_by_email(email):
                print(f"    = {email} (existe)")
                if role == Role.DOCTOR:
                    doctors.append(uow.users.get_by_email(email).id)
                continue
            user = make_user(tid, name, email, role, specialty)
            uow.users.save(user)
            print(f"    + {role.value} {email}")
            if role == Role.DOCTOR:
                doctors.append(user.id)
                uow.availability.save(weekday_availability(tid, user.id))

        uow.commit()

    # Insurers — seeded once per tenant (idempotent by name).
    uow = SqlAlchemyUnitOfWork(session, tid)
    insurer_ids: list[InsurerId | None] = []
    with uow:
        existing_insurers = {ins.name: ins.id for ins in uow.insurers.list()}
        for name, phone, email, address in INSURERS:
            if name in existing_insurers:
                insurer_ids.append(existing_insurers[name])
                continue
            insurer = Insurer(
                id=InsurerId.new(),
                tenant_id=tid,
                name=name,
                phone=phone,
                email=email,
                address=address,
            )
            uow.insurers.save(insurer)
            insurer_ids.append(insurer.id)
        uow.commit()
    insurer_ids.append(None)  # some patients have no insurer
    print(f"    + {len(INSURERS)} seguros")

    # Patients (15) — assigned round-robin to the tenant's doctors and insurers.
    if not doctors:
        doctors = [None]
    uow = SqlAlchemyUnitOfWork(session, tid)
    existing = uow.patients.list().total
    if existing >= 15:
        print(f"    pacientes: ya hay {existing}, omitido")
        return
    with uow:
        for i in range(15):
            code = codes.next_patient_code()
            uow.patients.save(
                make_patient(tid, code, i, doctors[i % len(doctors)])
            )
        uow.commit()
    print("    + 15 pacientes")


def main() -> None:
    session = get_session()

    print("Tenant 1: clinica-demo")
    t1 = get_or_create_tenant(session, "clinica-demo", "Clínica Demo SL", "Madrid · Centro")
    seed_tenant(
        session,
        t1,
        staff=[
            ("Dra. Elena Ruiz", "elena.ruiz@clinica-demo.test", Role.DOCTOR, "Cardiología"),
            ("Dr. Marco Vidal", "marco.vidal@clinica-demo.test", Role.DOCTOR, "Medicina General"),
            ("Lucía Méndez", "lucia.mendez@clinica-demo.test", Role.NURSE, "Enfermería"),
            ("Pedro Sanz", "pedro.sanz@clinica-demo.test", Role.NURSE, "Enfermería"),
            ("Sara Gil", "sara.gil@clinica-demo.test", Role.RECEPTIONIST, None),
            ("Hugo Castro", "hugo.castro@clinica-demo.test", Role.RECEPTIONIST, None),
        ],
        add_admin=True,  # admin@clinica-demo.test (idempotent)
    )

    print("Tenant 2: centro-norte")
    t2 = get_or_create_tenant(
        session, "centro-norte", "Centro Médico Norte SL", "Barcelona · Eixample"
    )
    seed_tenant(
        session,
        t2,
        staff=[
            ("Dra. Núria Soler", "nuria.soler@centro-norte.test", Role.DOCTOR, "Pediatría"),
            ("Dr. Iván Costa", "ivan.costa@centro-norte.test", Role.DOCTOR, "Traumatología"),
            ("Marta Roca", "marta.roca@centro-norte.test", Role.NURSE, "Enfermería"),
            ("Jordi Pla", "jordi.pla@centro-norte.test", Role.RECEPTIONIST, None),
        ],
        add_admin=True,  # new tenant needs an admin to be manageable
    )

    session.close()
    print("\nListo. Contraseña de todos los usuarios demo:", PASSWORD)


if __name__ == "__main__":
    main()
