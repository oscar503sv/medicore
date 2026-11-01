"""Seed rich, up-to-date demo data by replaying the clinic's history through the real use cases.

Per tenant: 2 admins, 5 doctors (each with a specialty and working hours), 1 nurse,
1 receptionist, 5 Salvadoran insurers and ~70 patients (some children and babies for
pediatrics, a few registered this week) with their vaccination histories (El Salvador's
national scheme). Everything is relative to the day the script runs:

* Past ~8 weeks: appointments booked by reception, confirmed, attended (consultation started,
  vitals + SOAP + CIE-11 diagnoses + prescriptions, then signed → medical record), plus
  cancellations and no-shows.
* Today: the morning already attended, the rest of the day confirmed — the dashboard shows
  real numbers and a comparison with last week.
* Next ~4 weeks: an agenda that thins out with distance, with some reschedules and
  cancellations, a doctor's vacation and an extra Saturday shift.
* Amendments (some by a covering doctor), uploaded documents (lab results, imaging…), a
  recently invited user whose role was corrected, and login history.

Because every action goes through its use case with a simulated clock, audit entries and
in-app notifications come out exactly as in real use. Older notifications are marked as read;
the last couple of days stay mostly unread.

Idempotent: re-running skips tenants that already have appointments. ``--reset`` wipes the
demo tenants first (cascade) and recreates them.

Usage:
    .venv/bin/python scripts/seed_demo.py [--reset]
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ApplicationError
from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    MarkNoShow,
    RescheduleAppointment,
)
from medicore.application.use_cases.availability import AddAvailabilityException
from medicore.application.use_cases.consultations import (
    AddDiagnosis,
    AddPrescriptionDraft,
    AutosaveConsultation,
    ConsultationPatch,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.application.use_cases.patients import CreatePatient, CreatePatientCommand
from medicore.application.use_cases.records import (
    AmendMedicalRecord,
    GetMedicalRecord,
    UploadDocument,
    UploadDocumentCommand,
)
from medicore.application.use_cases.users import InviteUser, InviteUserCommand, UpdateUserRole
from medicore.application.use_cases.vaccinations import (
    GetVaccinationCard,
    RecordVaccination,
    RecordVaccinationCommand,
    VoidVaccination,
)
from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.entities.insurer import Insurer
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.prescription import PrescriptionDraft
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import (
    AppointmentType,
    AvailabilityExceptionKind,
    DocumentKind,
    InjectionSite,
    PrescriptionStatus,
    Role,
    Sex,
    UserStatus,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
)
from medicore.domain.services.immunization import (
    SCHEDULE,
    VACCINES,
    ScheduledDose,
    add_months,
    applies_to,
)
from medicore.domain.shared.errors import DomainError
from medicore.domain.shared.identifiers import (
    AvailabilityId,
    ExceptionId,
    InsurerId,
    LocationId,
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
from medicore.infrastructure.persistence.models.notification import NotificationModel
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

PASSWORD = "demo1234"
HASHER = BcryptPasswordHasher()
RNG = random.Random(42)
TIMEZONE = "America/El_Salvador"

PAST_WEEKS = 8
FUTURE_WEEKS = 4
PATIENTS_PER_TENANT = 70
CHILDREN_PER_TENANT = 12
INFANTS_PER_TENANT = 5  # under 2: the busiest part of the vaccination scheme
NEW_PATIENTS_THIS_WEEK = 5

# ── reference data ────────────────────────────────────────────────────────────────────────
LAST_NAMES = [
    "Hernández", "López", "Martínez", "García", "Rodríguez", "Ramírez", "Flores", "Rivera",
    "Cruz", "Mejía", "Portillo", "Alvarado", "Rivas", "Menjívar", "Ayala", "Guevara",
    "Henríquez", "Cornejo", "Orellana", "Escobar", "Chávez", "Aguilar", "Bonilla", "Mendoza",
    "Quintanilla", "Pineda", "Romero", "Castillo",
]
FEMALE_NAMES = [
    "María", "Ana", "Rosa", "Carmen", "Karla", "Gabriela", "Daniela", "Claudia", "Patricia",
    "Sandra", "Yesenia", "Wendy", "Roxana", "Marta", "Silvia", "Fátima", "Krissia", "Elena",
]
MALE_NAMES = [
    "José", "Juan", "Carlos", "Mauricio", "Roberto", "Jorge", "Francisco", "Óscar", "Kevin",
    "Edwin", "William", "Mario", "René", "Rafael", "Nelson", "Salvador", "Ricardo", "Luis",
]
CHILD_FEMALE = ["Valentina", "Camila", "Ximena", "Sofía", "Isabella", "Fernanda"]
CHILD_MALE = ["Mateo", "Santiago", "Gael", "Diego", "Thiago", "Emiliano"]
COLONIAS = [
    "Escalón", "San Benito", "Miramonte", "Flor Blanca", "Médica", "Layco", "Centroamérica",
    "San Francisco", "Santa Elena", "Merliot",
]
BLOOD = ["O+", "O+", "A+", "A+", "B+", "O-", "A-", "AB+"]
ADULT_TAGS = [
    [], [], ["Hipertensión"], ["Diabetes tipo 2"], ["Asma"], ["Hipotiroidismo"], ["Migraña"],
    ["Hipertensión", "Dislipidemia"], ["Obesidad"], ["Ansiedad"], [],
]
CHILD_TAGS = [[], [], ["Asma"], ["Dermatitis atópica"], []]
ALLERGIES = [[], [], [], ["Penicilina"], ["Polen"], ["Frutos secos"], ["AINE"], ["Látex"]]

# Private health insurers operating in El Salvador (demo contact data is fictitious).
INSURERS = [
    ("Seguros SISA", "2200-1001", "gastos.medicos@sisa.test",
     "Alameda Dr. Manuel Enrique Araujo, San Salvador"),
    ("ASSA Seguros", "2200-1002", "salud@assa.test",
     "Calle Llama del Bosque Pte., Antiguo Cuscatlán"),
    ("Seguros del Pacífico", "2200-1003", "reclamos@pacifico.test",
     "Paseo General Escalón, San Salvador"),
    ("Pan-American Life", "2200-1004", "servicio@palig.test",
     "Boulevard del Hipódromo, Col. San Benito, San Salvador"),
    ("MAPFRE El Salvador", "2200-1005", "salud@mapfre-sv.test",
     "Alameda Roosevelt, San Salvador"),
]


@dataclass(frozen=True)
class Specialty:
    reasons: list[str]
    diagnoses: list[tuple[str, str]]  # CIE-11 (the demo clinics use CIE-11)
    meds: list[tuple[str, str, str, int]]  # drug, dose, schedule, days


MEDS_GENERAL = [
    ("Paracetamol", "500 mg", "c/8h si dolor o fiebre", 5),
    ("Ibuprofeno", "400 mg", "c/8h con alimentos", 7),
    ("Omeprazol", "20 mg", "1× día · ayunas", 28),
    ("Loratadina", "10 mg", "1× día", 15),
    ("Amoxicilina", "500 mg", "c/8h", 10),
]
SPECIALTIES: dict[str, Specialty] = {
    "Medicina General": Specialty(
        ["Revisión general", "Tos y fiebre", "Dolor de garganta", "Dolor abdominal",
         "Cefalea persistente", "Malestar general", "Chequeo anual", "Ardor al orinar"],
        [("CA07.0", "Infección respiratoria aguda de las vías altas, sitio no especificado"),
         ("CA02", "Faringitis aguda"), ("DA42.Z", "Gastritis, sin especificación"),
         ("GC08.Z", "Infección urinaria, localización y microbio patógeno no especificados"),
         ("8A80.Z", "Migraña, sin especificación"),
         ("1A40", "Gastroenteritis o colitis sin especificación del agente infeccioso")],
        MEDS_GENERAL,
    ),
    "Cardiología": Specialty(
        ["Control de hipertensión", "Palpitaciones", "Dolor torácico atípico",
         "Revisión de electrocardiograma", "Control de colesterol"],
        [("BA00.Z", "Hipertensión esencial, sin especificación"),
         ("5C80.0", "Hipercolesterolemia"), ("BC81", "Taquiarritmia supraventricular")],
        [("Enalapril", "20 mg", "1× día · mañana", 90), ("Amlodipino", "5 mg", "1× día", 90),
         ("Atorvastatina", "20 mg", "1× día · noche", 90), ("Ácido acetilsalicílico",
                                                             "100 mg", "1× día", 90)],
    ),
    "Pediatría": Specialty(
        ["Control de niño sano", "Fiebre", "Tos", "Vacunación", "Dolor de oído",
         "Erupción en la piel"],
        [("CA07.0", "Infección respiratoria aguda de las vías altas, sitio no especificado"),
         ("AB00", "Otitis media aguda"), ("EA80", "Eccema atópico"),
         ("1A40", "Gastroenteritis o colitis sin especificación del agente infeccioso")],
        [("Paracetamol jarabe", "15 mg/kg", "c/6h si fiebre", 5),
         ("Amoxicilina suspensión", "50 mg/kg/día", "c/8h", 10),
         ("Suero oral", "200 ml", "tras cada deposición", 3)],
    ),
    "Dermatología": Specialty(
        ["Acné", "Revisión de lunares", "Dermatitis", "Caída del cabello", "Picor persistente"],
        [("ED80", "Acné"), ("EA80", "Eccema atópico"), ("EA90", "Psoriasis"),
         ("ED70", "Alopecia o caída del pelo")],
        [("Peróxido de benzoilo gel", "5%", "1× día · noche", 60),
         ("Hidrocortisona crema", "1%", "2× día", 10), ("Cetirizina", "10 mg", "1× día", 15)],
    ),
    "Ginecología": Specialty(
        ["Control ginecológico anual", "Dolor pélvico", "Control prenatal",
         "Irregularidad menstrual", "Planificación familiar"],
        [("GA34.3", "Dismenorrea"), ("QA42", "Supervisión de embarazo normal"),
         ("GA20.0", "Amenorrea"),
         ("GC08.Z", "Infección urinaria, localización y microbio patógeno no especificados")],
        [("Ácido fólico", "5 mg", "1× día", 90), ("Ibuprofeno", "600 mg", "c/8h", 5),
         ("Hierro", "80 mg", "1× día", 60)],
    ),
    "Traumatología": Specialty(
        ["Dolor lumbar", "Dolor de rodilla", "Esguince de tobillo", "Dolor de hombro",
         "Control post-fractura"],
        [("ME84.2", "Dolor lumbar"), ("FA01", "Osteoartritis de la rodilla"),
         ("ND14.7", "Distensión o esguince del tobillo"), ("FB53", "Lesiones del hombro")],
        [("Ibuprofeno", "600 mg", "c/8h con alimentos", 10),
         ("Metocarbamol", "500 mg", "c/8h", 7), ("Paracetamol", "1 g", "c/8h", 10)],
    ),
    "Endocrinología": Specialty(
        ["Seguimiento diabetes", "Control de tiroides", "Control de peso",
         "Resultados de laboratorio"],
        [("5A11", "Diabetes mellitus tipo 2"), ("5A00.Z", "Hipotiroidismo, sin especificación"),
         ("5B81", "Obesidad"), ("5C80.0", "Hipercolesterolemia")],
        [("Metformina", "850 mg", "2× día con comidas", 90), ("Levotiroxina", "50 mcg",
                                                              "1× día · ayunas", 90),
         ("Atorvastatina", "10 mg", "1× día · noche", 90)],
    ),
}

# Per tenant: (name, email_local, role, specialty, works_afternoons). Admin is added apart.
STAFF = {
    "clinica-demo": [
        ("Dra. Elena Ruiz", "elena.ruiz", Role.DOCTOR, "Cardiología", True),
        ("Dr. Marco Vidal", "marco.vidal", Role.DOCTOR, "Medicina General", True),
        ("Dra. Paula Méndez", "paula.mendez", Role.DOCTOR, "Pediatría", False),
        ("Dr. Andrés Soto", "andres.soto", Role.DOCTOR, "Dermatología", True),
        ("Dra. Carla Núñez", "carla.nunez", Role.DOCTOR, "Ginecología", False),
        ("Lucía Méndez", "lucia.mendez", Role.NURSE, None, True),
        ("Sara Gil", "sara.gil", Role.RECEPTIONIST, None, True),
        ("Raúl Herrera", "raul.herrera", Role.ADMIN, None, True),
    ],
    "centro-norte": [
        ("Dra. Karla Henríquez", "karla.henriquez", Role.DOCTOR, "Pediatría", False),
        ("Dr. José Alfaro", "jose.alfaro", Role.DOCTOR, "Traumatología", True),
        ("Dr. Mauricio Cruz", "mauricio.cruz", Role.DOCTOR, "Medicina General", True),
        ("Dra. Ana Lucía Portillo", "analucia.portillo", Role.DOCTOR, "Endocrinología", False),
        ("Dr. Roberto Menjívar", "roberto.menjivar", Role.DOCTOR, "Cardiología", True),
        ("Marta Ayala", "marta.ayala", Role.NURSE, None, True),
        ("Jorge Pleitez", "jorge.pleitez", Role.RECEPTIONIST, None, True),
        ("Carolina Guevara", "carolina.guevara", Role.ADMIN, None, True),
    ],
}
# A user invited a few days ago by the second admin (as nurse, then corrected to reception).
INVITED = {
    "clinica-demo": ("Andrea Molina", "andrea.molina"),
    "centro-norte": ("Gabriel Serrano", "gabriel.serrano"),
}
DOCUMENTS = [
    (DocumentKind.LAB, "Hemograma completo.pdf", "application/pdf"),
    (DocumentKind.LAB, "Perfil lipídico.pdf", "application/pdf"),
    (DocumentKind.LAB, "Glucosa y HbA1c.pdf", "application/pdf"),
    (DocumentKind.LAB, "Examen general de orina.pdf", "application/pdf"),
    (DocumentKind.IMAGING, "Radiografía de tórax.jpg", "image/jpeg"),
    (DocumentKind.IMAGING, "Ecografía abdominal.pdf", "application/pdf"),
    (DocumentKind.IMAGING, "Electrocardiograma.png", "image/png"),
    (DocumentKind.CONSENT, "Consentimiento informado.pdf", "application/pdf"),
    (DocumentKind.OTHER, "Referencia de especialista.pdf", "application/pdf"),
    (DocumentKind.RX, "Receta externa.jpg", "image/jpeg"),
]


# ── simulated clock ───────────────────────────────────────────────────────────────────────
class SimClock:
    """A settable clock. Times are given as clinic wall-clock and returned as UTC instants,
    like ``SystemClock``, so use cases convert them back with the tenant's timezone."""

    def __init__(self, tz: ZoneInfo) -> None:
        self.tz = tz
        self._now = datetime.now(UTC)

    def at(self, local: datetime) -> SimClock:
        self._now = local.replace(tzinfo=self.tz).astimezone(UTC)
        return self

    def now(self) -> datetime:
        return self._now


@dataclass
class Clinic:
    """Everything the activity generators need about one tenant."""

    session: object
    tenant: Tenant
    clock: SimClock
    now: datetime  # clinic wall-clock when the script runs
    admin: User
    second_admin: User
    doctors: list[User]
    specialty: dict[UserId, str]
    nurse: User
    reception: User
    insurer_ids: list[InsurerId]
    patients: list[Patient] = field(default_factory=list)
    signed: list[MedicalRecord] = field(default_factory=list)
    taken: set[tuple[UserId, datetime]] = field(default_factory=set)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def tid(self) -> TenantId:
        return self.tenant.id

    @property
    def today(self) -> date:
        return self.now.date()

    def uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session, self.tid)

    def codes(self) -> DbSequentialCodeGenerator:
        return DbSequentialCodeGenerator(self.session, self.tid.value)

    def at(self, local: datetime) -> SimClock:
        return self.clock.at(local)

    def count(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n


def actor(c: Clinic, user: User) -> ActorContext:
    return ActorContext(
        user_id=user.id, tenant_id=c.tid, role=user.role, ip_address="10.0.0.12",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0",
    )


# ── setup: tenant, staff, insurers ────────────────────────────────────────────────────────
def availability_for(tid: TenantId, doctor_id: UserId, afternoons: bool) -> DoctorAvailability:
    """Mon–Fri 09:00–14:00, plus 16:00–19:00 for doctors who work afternoons."""
    blocks = [TimeRange(time(9, 0), time(14, 0))]
    if afternoons:
        blocks.append(TimeRange(time(16, 0), time(19, 0)))
    weekly = [WeeklyDay(day_of_week=d, enabled=d < 5, blocks=list(blocks) if d < 5 else [])
              for d in range(7)]
    return DoctorAvailability(
        id=AvailabilityId.new(), tenant_id=tid, doctor_id=doctor_id, weekly=weekly,
        rules=BookingRules(slot_minutes=30),
    )


def make_user(tid: TenantId, name: str, email: str, role: Role, specialty=None) -> User:
    first = name.replace("Dr. ", "").replace("Dra. ", "").split()[0]
    female = name.startswith("Dra. ") or first.lower().endswith("a")
    return User(
        id=UserId.new(), tenant_id=tid, name=name, email=email,
        password_hash=HASHER.hash(PASSWORD), role=role, status=UserStatus.ACTIVE,
        sex=Sex.FEMALE if female else Sex.MALE, specialty=specialty,
        phone=f"7{RNG.randint(100, 999)}-{RNG.randint(1000, 9999)}",
    )


def get_or_create_tenant(
    session, slug: str, legal_name: str, tax_id: str, location: str
) -> Tenant:
    row = session.query(TenantModel).filter(TenantModel.slug == slug).first()
    if row:
        print(f"  tenant '{slug}' ya existe")
        tid = TenantId.parse(row.id)
        return SqlAlchemyUnitOfWork(session, tid).tenants.get_by_id(tid)
    tid = TenantId.new()
    tenant = Tenant(
        id=tid, legal_name=legal_name, tax_id=tax_id, slug=Slug(slug), timezone=TIMEZONE,
        locations=[Location(id=LocationId.new(), tenant_id=tid, name=location, is_primary=True)],
    )
    uow = SqlAlchemyUnitOfWork(session, tid)
    with uow:
        uow.tenants.save(tenant)
        uow.commit()
    print(f"  tenant '{slug}' creado")
    return tenant


def seed_staff(session, tenant: Tenant) -> dict:
    tid = tenant.id
    uow = SqlAlchemyUnitOfWork(session, tid)
    out: dict = {"doctors": [], "specialty": {}, "admins": []}
    with uow:
        email = f"admin@{tenant.slug}.test"
        admin = uow.users.get_by_email(email)
        if admin is None:
            admin = make_user(tid, "Admin Demo", email, Role.ADMIN)
            uow.users.save(admin)
        out["admins"].append(admin)
        for name, local, role, specialty, afternoons in STAFF[str(tenant.slug)]:
            email = f"{local}@{tenant.slug}.test"
            user = uow.users.get_by_email(email)
            if user is None:
                user = make_user(tid, name, email, role, specialty)
                uow.users.save(user)
                if role == Role.DOCTOR:
                    uow.availability.save(availability_for(tid, user.id, afternoons))
            if role == Role.DOCTOR:
                out["doctors"].append(user)
                out["specialty"][user.id] = specialty
            elif role == Role.NURSE:
                out["nurse"] = user
            elif role == Role.RECEPTIONIST:
                out["reception"] = user
            else:
                out["admins"].append(user)
        uow.commit()
    return out


def seed_insurers(session, tid: TenantId) -> list[InsurerId]:
    uow = SqlAlchemyUnitOfWork(session, tid)
    with uow:
        existing = {ins.name: ins.id for ins in uow.insurers.list()}
        ids = []
        for name, phone, email, address in INSURERS:
            if name not in existing:
                ins = Insurer(id=InsurerId.new(), tenant_id=tid, name=name, phone=phone,
                              email=email, address=address)
                uow.insurers.save(ins)
                existing[name] = ins.id
            ids.append(existing[name])
        uow.commit()
    return ids


# ── patients ──────────────────────────────────────────────────────────────────────────────
def seed_patients(c: Clinic) -> None:
    pediatrician = next(d for d in c.doctors if c.specialty[d.id] == "Pediatría")
    adult_doctors = [d for d in c.doctors if d.id != pediatrician.id]
    used: set[str] = set()
    for i in range(PATIENTS_PER_TENANT):
        child = i < CHILDREN_PER_TENANT
        female = RNG.random() < (0.5 if child else 0.58)
        names = (CHILD_FEMALE if female else CHILD_MALE) if child else (
            FEMALE_NAMES if female else MALE_NAMES)
        while True:
            first = RNG.choice(names)
            last = f"{RNG.choice(LAST_NAMES)} {RNG.choice(LAST_NAMES)}"
            if f"{first} {last}" not in used:
                used.add(f"{first} {last}")
                break
        if child and i < INFANTS_PER_TENANT:
            born = c.today - timedelta(days=RNG.randint(45, 700))
        else:
            age = RNG.randint(2, 13) if child else RNG.randint(18, 84)
            born = c.today - timedelta(days=age * 365 + RNG.randint(0, 364))
        if child:
            doctor = pediatrician
        elif not female:
            doctor = RNG.choice([d for d in adult_doctors if c.specialty[d.id] != "Ginecología"])
        else:
            doctor = RNG.choice(adult_doctors)
        # Most patients registered months ago; a handful this week (dashboard growth).
        if i >= PATIENTS_PER_TENANT - NEW_PATIENTS_THIS_WEEK:
            created = c.now - timedelta(days=RNG.randint(0, 6), hours=RNG.randint(1, 8))
        else:
            created = c.now - timedelta(days=RNG.randint(PAST_WEEKS * 7 + 5, 240))
        created = created.replace(hour=RNG.randint(8, 17), minute=RNG.choice([0, 15, 30, 45]))
        if created > c.now:
            created -= timedelta(days=1)
        if created.date() <= born:  # a baby is registered after being born
            created = datetime.combine(born + timedelta(days=RNG.randint(3, 15)), created.time())
        handle = f"{first}.{last.split()[0]}".lower().translate(str.maketrans("áéíóúñü", "aeiounu"))
        cmd = CreatePatientCommand(
            first_name=first, last_name=last, sex=Sex.FEMALE if female else Sex.MALE,
            date_of_birth=born, blood_type=BloodType(RNG.choice(BLOOD)),
            primary_doctor_id=doctor.id,
            tags=tuple(RNG.choice(CHILD_TAGS if child else ADULT_TAGS)),
            allergies=tuple(RNG.choice(ALLERGIES)),
            contact=ContactInfo(
                phone=f"7{RNG.randint(100, 999)}-{RNG.randint(1000, 9999)}",
                email=None if child else f"{handle}@example.com",
                address=f"Calle {RNG.choice(LAST_NAMES)} #{RNG.randint(1, 120)}, "
                        f"Col. {RNG.choice(COLONIAS)}",
                emergency_contact_name=f"{RNG.choice(FEMALE_NAMES + MALE_NAMES)} "
                                       f"{last.split()[0]}",
                emergency_contact_phone=f"7{RNG.randint(100, 999)}-{RNG.randint(1000, 9999)}",
            ),
        )
        patient = CreatePatient(c.uow(), c.codes(), c.at(created)).execute(
            actor(c, c.reception), cmd)
        c.patients.append(patient)
    print(f"    + {len(c.patients)} pacientes ({CHILDREN_PER_TENANT} niños, "
          f"{NEW_PATIENTS_THIS_WEEK} registrados esta semana)")


# ── vaccination ───────────────────────────────────────────────────────────────────────────
def _months(birth: date, on: date) -> int:
    return (on.year - birth.year) * 12 + on.month - birth.month - (on.day < birth.day)


def seed_vaccinations(c: Clinic) -> None:
    """Vaccination histories recorded by the nurse through ``RecordVaccination``.

    Doses before the patient registered here are copied from their card (external, no lot);
    later ones are given at the clinic with a lot. Children are mostly up to date, some are
    behind on their latest doses (overdue in the worklist); adults have a Td within 10 years
    more often than not, and over-60s their yearly influenza (a few refused it). Finally, a
    couple of doses given this morning and one entry voided and re-recorded.
    """
    nurse = actor(c, c.nurse)
    lots = {code: f"{code[:3]}{RNG.randint(100, 999)}{RNG.choice('ABCDEFGH')}"
            for code in VACCINES}
    latest = c.now - timedelta(minutes=5)

    def record(patient: Patient, dose: ScheduledDose, on: date, *, here: bool | None = None,
               outcome=VaccinationOutcome.ADMINISTERED, notes=None, lot=None,
               at: datetime | None = None):
        since = patient.created_at.astimezone(c.clock.tz).replace(tzinfo=None)
        if here is None:
            here = on >= since.date()
        if at is None:
            at = (datetime.combine(on, time(RNG.randint(8, 15), RNG.choice([0, 15, 30, 45])))
                  if here else since + timedelta(minutes=20))  # card copied when registering
        at = min(at, latest)
        given_here = here and outcome == VaccinationOutcome.ADMINISTERED
        route = VACCINES[dose.vaccine].route
        infant = (on - patient.date_of_birth).days < 3 * 365
        site = (InjectionSite.MOUTH if route == VaccineRoute.ORAL
                else RNG.choice([InjectionSite.LEFT_THIGH, InjectionSite.RIGHT_THIGH]) if infant
                else RNG.choice([InjectionSite.LEFT_ARM, InjectionSite.RIGHT_ARM]))
        cmd = RecordVaccinationCommand(
            patient_id=patient.id, vaccine_code=dose.vaccine, dose_key=dose.key,
            outcome=outcome, occurred_on=on,
            source=VaccinationSource.CLINIC if here else VaccinationSource.EXTERNAL,
            lot=(lot or lots[dose.vaccine]) if given_here else None,
            site=site if given_here else None, notes=notes,
        )
        c.count("vacunas registradas")
        return RecordVaccination(c.uow(), c.at(at)).execute(nurse, cmd)

    by_key = {d.key: d for d in SCHEDULE}
    for patient in c.patients:
        birth, sex = patient.date_of_birth, patient.sex
        age_m = _months(birth, c.today)
        behind = RNG.random() < 0.3
        for dose in SCHEDULE:
            if not dose.routine or dose.repeat_months or not applies_to(dose, sex):
                continue
            due = add_months(birth, dose.age_months)
            limit = add_months(birth, dose.max_age_months) if dose.max_age_months else None
            if due > c.today or (dose.stage == "childhood" and age_m > 13 * 12):
                continue  # not due yet / an adult's childhood card isn't on file
            if limit and limit < c.today and dose.stage != "childhood":
                continue  # e.g. HPV for a woman past the window: never given
            if behind and (c.today - due).days < 240:
                continue  # missed the latest doses → overdue in the worklist
            if RNG.random() < (0.05 if dose.stage == "childhood" else 0.5):
                continue
            on = min(due + timedelta(days=RNG.randint(0, 21)), c.today)
            if limit:
                on = min(on, limit)
            record(patient, dose, on)

        # Periodic doses: the last one within its period (or none → due/overdue).
        if age_m >= 10 * 12 and RNG.random() < 0.65:
            start = add_months(birth, 10 * 12)
            on = max(start, c.today - timedelta(days=RNG.randint(30, 9 * 365)))
            record(patient, by_key["TD-1"], on)
        if 18 <= age_m < 60 and RNG.random() < 0.7:
            record(patient, by_key["INFLU_PED-Y"], c.today - timedelta(days=RNG.randint(20, 300)))
        if age_m >= 60 * 12:
            roll = RNG.random()
            if roll < 0.6:
                record(patient, by_key["INFLU-Y"], c.today - timedelta(days=RNG.randint(20, 300)))
            elif roll < 0.68:
                record(patient, by_key["INFLU-Y"], c.today - timedelta(days=RNG.randint(5, 60)),
                       outcome=VaccinationOutcome.REFUSED, here=True,
                       notes="Prefiere no vacunarse esta temporada.")

    # This morning: the next pending doses of a couple of babies.
    morning = c.now.replace(hour=8, minute=30) if c.now.hour >= 9 else c.now - timedelta(hours=1)
    babies = [p for p in c.patients if _months(p.date_of_birth, c.today) < 24]
    for k, baby in enumerate(babies[:2]):
        card = GetVaccinationCard(c.uow(), c.at(c.now)).execute(nurse, baby.id)
        for state in [s for s in card.states if s.status in ("due", "overdue")][:2]:
            when = morning + timedelta(minutes=40 * k + RNG.randint(0, 10))
            record(baby, state.dose, when.date(), here=True, at=when)

    # A mistyped lot, voided and recorded again.
    adult = next(p for p in c.patients if _months(p.date_of_birth, c.today) >= 30 * 12)
    when = c.now - timedelta(days=3)
    if when.hour < 8:
        when = when.replace(hour=10)
    key = "INFLU-Y" if _months(adult.date_of_birth, c.today) >= 60 * 12 else "TD-1"
    wrong = record(adult, by_key[key], when.date(), here=True, at=when, lot="XXX000")
    VoidVaccination(c.uow(), c.at(when + timedelta(minutes=12))).execute(
        nurse, wrong.id, "Lote mal digitado")
    record(adult, by_key[wrong.dose_key], when.date(), here=True,  # periodic: may repeat
           at=when + timedelta(minutes=14))
    c.count("vacunas anuladas")


# ── availability exceptions ───────────────────────────────────────────────────────────────
def seed_exceptions(c: Clinic) -> None:
    def add(doctor: User, on: date, kind, reason: str, blocks=()) -> None:
        exc = AvailabilityException(id=ExceptionId.new(), date=on, kind=kind, reason=reason,
                                    blocks=list(blocks))
        AddAvailabilityException(c.uow(), c.at(c.now - timedelta(days=30))).execute(
            actor(c, doctor), exc)

    monday = c.today - timedelta(days=c.today.weekday())
    general = next(d for d in c.doctors if c.specialty[d.id] == "Medicina General")
    # Vacation (3 weekdays the week after next), a past congress day and an extra Saturday.
    for k in range(3):
        add(c.doctors[2], monday + timedelta(weeks=2, days=k), AvailabilityExceptionKind.OFF,
            "Vacaciones")
    add(c.doctors[0], monday - timedelta(weeks=2) + timedelta(days=2),
        AvailabilityExceptionKind.OFF, "Congreso médico")
    saturday = monday + timedelta(days=5 if c.today.weekday() <= 5 else 12)
    add(general, saturday, AvailabilityExceptionKind.EXTRA, "Jornada de vacunación",
        [TimeRange(time(9, 0), time(13, 0))])


# ── appointments and consultations ────────────────────────────────────────────────────────
def day_slots(c: Clinic, doctor: User, on: date) -> list[datetime]:
    av = c.uow().availability.get_by_doctor(doctor.id)
    exc = av.exception_on(on)
    if exc is not None and exc.kind == AvailabilityExceptionKind.OFF:
        return []
    blocks = exc.blocks if exc is not None else av.day(on.weekday()).blocks
    if exc is None and not av.day(on.weekday()).enabled:
        return []
    slots = []
    for b in blocks:
        t = datetime.combine(on, b.start)
        while t + timedelta(minutes=30) <= datetime.combine(on, b.end):
            slots.append(t)
            t += timedelta(minutes=30)
    return slots


def daily_load(c: Clinic, on: date) -> float:
    """Share of a doctor's slots that get booked: busier around today, thinner far ahead."""
    delta = (on - c.today).days
    if delta < -14:
        return RNG.uniform(0.3, 0.5)
    if delta <= 0:
        return RNG.uniform(0.5, 0.7)
    if delta <= 7:
        return RNG.uniform(0.45, 0.65)
    if delta <= 14:
        return RNG.uniform(0.2, 0.35)
    return RNG.uniform(0.05, 0.2)


def pick_patient(c: Clinic, doctor: User, before: datetime) -> Patient | None:
    specialty = c.specialty[doctor.id]
    eligible = [p for p in c.patients
                if p.created_at.astimezone(c.clock.tz).replace(tzinfo=None) < before]
    if specialty == "Pediatría":
        eligible = [p for p in eligible if p.age(c.today) < 14]
    else:
        eligible = [p for p in eligible if p.age(c.today) >= 14]
        if specialty == "Ginecología":
            eligible = [p for p in eligible if p.sex == Sex.FEMALE]
    if not eligible:
        return None
    own = [p for p in eligible if p.primary_doctor_id == doctor.id]
    return RNG.choice(own if own and RNG.random() < 0.6 else eligible)


def insurer_for(c: Clinic, patient: Patient):
    n = int(patient.code.split("-")[-1]) % (len(c.insurer_ids) + 1)
    return None if n == len(c.insurer_ids) else c.insurer_ids[n]


def book(c: Clinic, doctor: User, start: datetime):
    patient = pick_patient(c, doctor, start - timedelta(days=1))
    if patient is None:
        return None
    patient_since = patient.created_at.astimezone(c.clock.tz).replace(tzinfo=None)
    booked = start - timedelta(days=RNG.randint(1, 12), hours=RNG.randint(0, 6))
    latest = min(c.now - timedelta(minutes=RNG.randint(30, 600)), start - timedelta(hours=2))
    if booked > latest:
        # Future appointments were booked over the last two weeks, not all just now.
        booked = c.now - timedelta(days=RNG.uniform(0.2, 14))
    booked = min(max(booked, patient_since + timedelta(hours=2)), latest)
    booked = booked.replace(hour=RNG.randint(8, 17), minute=RNG.choice([0, 10, 25, 40, 55]))
    booked = min(booked, latest)
    booked = booked.replace(second=0, microsecond=0)
    cmd = CreateAppointmentCommand(
        patient_id=patient.id, doctor_id=doctor.id,
        location_id=c.tenant.primary_location.id,
        type=AppointmentType.CONSULT, scheduled_start=start,
        reason=RNG.choice(SPECIALTIES[c.specialty[doctor.id]].reasons),
        insurance_id=insurer_for(c, patient),
    )
    try:
        appt = CreateAppointment(c.uow(), c.codes(), c.at(booked)).execute(
            actor(c, c.reception), cmd)
    except (ApplicationError, DomainError):
        return None
    c.taken.add((doctor.id, start))
    c.count("citas")
    return appt, patient, booked


def vitals_for(patient: Patient, on: date) -> Vitals:
    age = patient.age(on)
    if age < 14:
        return Vitals(
            heart_rate=RNG.randint(80, 120), spo2=RNG.randint(96, 100),
            temperature=Decimal(f"{RNG.randint(362, 389) / 10:.1f}"),
            weight=Decimal(f"{max(8.0, age * 3.2 + RNG.uniform(6, 10)):.1f}"),
            height=Decimal(int(min(165, 70 + age * 6.5 + RNG.randint(-4, 4)))),
        )
    return Vitals(
        blood_pressure=f"{RNG.randint(108, 152)}/{RNG.randint(66, 96)}",
        heart_rate=RNG.randint(58, 98), spo2=RNG.randint(94, 100),
        temperature=Decimal(f"{RNG.randint(360, 382) / 10:.1f}"),
        weight=Decimal(f"{RNG.randint(480, 1050) / 10:.1f}"),
        glucose=RNG.randint(78, 165), height=Decimal(RNG.randint(150, 192)),
    )


def soap_for(reason: str, dx_label: str) -> SoapNote:
    return SoapNote(
        subjective=RNG.choice([
            f"Acude por {reason.lower()}. Evolución de {RNG.randint(2, 14)} días.",
            f"Refiere {reason.lower()}; sin otros síntomas asociados.",
            f"Consulta por {reason.lower()}. Niega fiebre ni pérdida de peso.",
        ]),
        objective=RNG.choice([
            "Buen estado general. Constantes estables. Exploración sin hallazgos de alarma.",
            "Consciente y orientado. Auscultación normal. Abdomen blando y depresible.",
            "Paciente colaborador, hidratado. Exploración física dentro de la normalidad.",
        ]),
        assessment=f"Cuadro compatible con {dx_label.lower()}.",
        plan=RNG.choice([
            "Tratamiento indicado y control en 2 semanas. Signos de alarma explicados.",
            "Se solicitan análisis de control. Revisión con resultados.",
            "Medidas higiénico-dietéticas, tratamiento pautado y seguimiento en 1 mes.",
        ]),
    )


def attend(c: Clinic, doctor: User, appt, patient: Patient) -> None:
    """Start, document and sign the consultation like the doctor would in the app."""
    me = actor(c, doctor)
    start = appt.scheduled_start + timedelta(minutes=RNG.randint(0, 12))
    consultation = StartConsultation(c.uow(), c.at(start)).execute(me, appt.id)
    spec = SPECIALTIES[c.specialty[doctor.id]]
    dx = RNG.sample(spec.diagnoses, 1 if RNG.random() < 0.75 else 2)
    AutosaveConsultation(c.uow(), c.at(start + timedelta(minutes=6))).execute(
        me, consultation.id,
        ConsultationPatch(vitals=vitals_for(patient, start.date()), soap=soap_for(
            appt.reason, dx[0][1])),
    )
    for code, label in dx:
        AddDiagnosis(c.uow(), c.at(start + timedelta(minutes=10))).execute(
            me, consultation.id, IcdCode(code, label))
    for drug, dose, schedule, days in RNG.sample(spec.meds, RNG.choice([0, 1, 1, 2])):
        AddPrescriptionDraft(c.uow(), c.at(start + timedelta(minutes=14))).execute(
            me, consultation.id,
            PrescriptionDraft(drug=drug, dose=dose, schedule=schedule, duration_days=days,
                              start_date=start.date()),
        )
    record = SignConsultation(c.uow(), c.codes(),
                              c.at(start + timedelta(minutes=RNG.randint(18, 27)))).execute(
        me, SignConsultationCommand(consultation_id=consultation.id))
    c.signed.append(record)
    c.count("consultas firmadas")
    reopened = start + timedelta(days=RNG.randint(1, 6), hours=2)
    if RNG.random() < 0.3 and reopened < c.now:  # reopened later (audited as record.viewed)
        GetMedicalRecord(c.uow(), c.at(reopened)).execute(me, record.id)


def seed_agenda(c: Clinic) -> None:
    first = c.today - timedelta(weeks=PAST_WEEKS)
    last = c.today + timedelta(weeks=FUTURE_WEEKS)
    day = first
    while day <= last:
        for doctor in c.doctors:
            slots = day_slots(c, doctor, day)
            if not slots:
                continue
            chosen = sorted(RNG.sample(slots, round(len(slots) * daily_load(c, day))))
            for start in chosen:
                if (doctor.id, start) in c.taken:
                    continue
                booked = book(c, doctor, start)
                if booked is None:
                    continue
                appt, patient, booked_at = booked
                play_out(c, doctor, appt, patient, booked_at)
        if day.weekday() == 0:
            print(f"      semana del {day:%d/%m}: {c.stats.get('citas', 0)} citas acumuladas")
        day += timedelta(days=1)


def play_out(c: Clinic, doctor: User, appt, patient: Patient, booked_at: datetime) -> None:
    """What happened (or is expected to happen) to an appointment after it was booked."""
    rec = actor(c, c.reception)
    start = appt.scheduled_start
    roll = RNG.random()
    finished = start + timedelta(minutes=30) <= c.now

    # Cancelled somewhere between booking and the appointment (or before now).
    if roll < 0.06:
        when = booked_at + (min(start, c.now) - booked_at) * RNG.uniform(0.3, 0.9)
        CancelAppointment(c.uow(), c.at(when)).execute(rec, appt.id)
        c.count("canceladas")
        return

    # Upcoming appointments: some get moved to a later free slot, some get confirmed.
    if not finished:
        if roll < 0.12 and start.date() > c.today:
            for _ in range(6):
                target = start + timedelta(days=RNG.randint(1, 6))
                slots = [s for s in day_slots(c, doctor, target.date())
                         if (doctor.id, s) not in c.taken]
                if not slots:
                    continue
                new_start = RNG.choice(slots)
                try:
                    when = booked_at + (c.now - booked_at) * RNG.uniform(0.3, 0.9)
                    RescheduleAppointment(c.uow(), c.at(when)).execute(rec, appt.id, new_start)
                except (ApplicationError, DomainError):
                    continue
                c.taken.add((doctor.id, new_start))
                c.count("reprogramadas")
                break
            return
        if start.date() <= c.today + timedelta(days=3) and RNG.random() < 0.7:
            confirm_at = min(c.now - timedelta(minutes=RNG.randint(10, 480)),
                             start - timedelta(hours=RNG.randint(4, 26)))
            confirm_at = max(confirm_at, booked_at + timedelta(hours=1))
            if confirm_at < start and confirm_at <= c.now:
                ConfirmAppointment(c.uow(), c.at(confirm_at)).execute(rec, appt.id)
        return

    # Past appointments: mostly confirmed the day before, then attended or missed.
    if RNG.random() < 0.8:
        confirm_at = max(booked_at + timedelta(minutes=30), start - timedelta(hours=RNG.randint(
            16, 30)))
        if confirm_at < start:
            ConfirmAppointment(c.uow(), c.at(confirm_at)).execute(rec, appt.id)
    if roll < 0.11:
        MarkNoShow(c.uow(), c.at(start + timedelta(minutes=25))).execute(rec, appt.id)
        c.count("no-show")
        return
    attend(c, doctor, appt, patient)


# ── amendments, documents, users, logins ──────────────────────────────────────────────────
def seed_amendments(c: Clinic) -> None:
    recent = [r for r in c.signed if r.signed_at.date() >= c.today - timedelta(days=21)
              and r.signed_at.date() < c.today - timedelta(days=1)]
    RNG.shuffle(recent)
    by_id = {d.id: d for d in c.doctors}
    covering = 0
    for record in recent[:12]:
        author = by_id[record.author_id]
        # About a third are added by a covering colleague → the author gets notified.
        if covering < 4 and c.specialty[author.id] != "Pediatría":
            amender = RNG.choice([d for d in c.doctors if d.id != author.id
                                  and c.specialty[d.id] != "Pediatría"])
            covering += 1
        else:
            amender = author
        when_utc = record.signed_at + timedelta(days=RNG.randint(1, 4), hours=RNG.randint(1, 5))
        when = min(when_utc.astimezone(c.clock.tz).replace(tzinfo=None),
                   c.now - timedelta(hours=1))
        soap = SoapNote(
            subjective=record.soap.subjective, objective=record.soap.objective,
            assessment=record.soap.assessment,
            plan=record.soap.plan + " Adenda: " + RNG.choice([
                "resultados de laboratorio dentro de la normalidad.",
                "se ajusta la dosis según evolución telefónica.",
                "paciente refiere mejoría; se mantiene el tratamiento.",
                "se añade derivación a especialista.",
            ]),
        )
        AmendMedicalRecord(c.uow(), c.at(when)).execute(actor(c, amender), record.id, soap=soap)
        c.count("enmiendas")


def seed_documents(c: Clinic) -> None:
    candidates = [r for r in c.signed if r.signed_at.date() >= c.today - timedelta(days=42)]
    for record in RNG.sample(candidates, min(30, len(candidates))):
        kind, name, mime = RNG.choice(DOCUMENTS)
        signed_local = record.signed_at.astimezone(c.clock.tz).replace(tzinfo=None)
        when = min(signed_local + timedelta(days=RNG.randint(0, 5), hours=RNG.randint(1, 6)),
                   c.now - timedelta(minutes=RNG.randint(20, 300)))
        # Mostly the nurse; sometimes another doctor (e.g. the one who ordered the test).
        uploader = c.nurse if RNG.random() < 0.7 else RNG.choice(c.doctors)
        UploadDocument(c.uow(), c.at(when)).execute(actor(c, uploader), UploadDocumentCommand(
            patient_id=record.patient_id, file_name=name, kind=kind, mime_type=mime,
            size_bytes=RNG.randint(80_000, 3_500_000),
            storage_key=f"demo/{c.tenant.slug}/{record.code.lower()}-{RNG.randint(1000, 9999)}",
            record_id=record.id if RNG.random() < 0.6 else None,
        ))
        c.count("documentos")


def seed_users(c: Clinic) -> None:
    name, local = INVITED[str(c.tenant.slug)]
    second = actor(c, c.second_admin)
    user = InviteUser(c.uow(), HASHER, c.at(c.now - timedelta(days=4, hours=3))).execute(
        second, InviteUserCommand(name=name, email=f"{local}@{c.tenant.slug}.test",
                                  role=Role.NURSE, password=PASSWORD))
    UpdateUserRole(c.uow(), c.at(c.now - timedelta(hours=5))).execute(
        second, user.id, Role.RECEPTIONIST)


def seed_logins(c: Clinic) -> None:
    staff = [c.admin, c.second_admin, c.nurse, c.reception, *c.doctors]
    uow = c.uow()
    with uow:
        for back in range(14, -1, -1):
            day = c.today - timedelta(days=back)
            if day.weekday() >= 5:
                continue
            for user in staff:
                if RNG.random() < 0.15:
                    continue
                local = datetime.combine(day, time(8, RNG.randint(0, 55)))
                if local > c.now:
                    continue
                uow.audit.append(audit_entry(
                    actor(c, user), local.replace(tzinfo=c.clock.tz).astimezone(UTC),
                    "auth.login", "User", str(user.id)))
        uow.commit()


# ── finishing touches ─────────────────────────────────────────────────────────────────────
def finish(c: Clinic) -> None:
    """Expire finished prescriptions and mark older notifications as read."""
    uow = c.uow()
    with uow:
        expired = 0
        for patient in c.patients:
            for rx in uow.prescriptions.list_by_patient(patient.id):
                if rx.status == PrescriptionStatus.ACTIVE and rx.is_expired_on(c.today):
                    rx.complete()
                    uow.prescriptions.save(rx)
                    expired += 1
        uow.commit()
    now_utc = c.clock.at(c.now).now()
    session = c.session
    rows = session.execute(
        select(NotificationModel.id, NotificationModel.created_at)
        .where(NotificationModel.tenant_id == c.tid.value)
    ).all()
    for nid, created in rows:
        age = now_utc - created
        if age > timedelta(days=2) or (age > timedelta(hours=6) and RNG.random() < 0.4):
            session.execute(update(NotificationModel).where(NotificationModel.id == nid).values(
                read_at=created + timedelta(minutes=RNG.randint(5, 600))))
    session.commit()
    c.count("recetas finalizadas", expired)
    unread = sum(1 for _, created in rows if now_utc - created <= timedelta(days=2))
    c.count("notificaciones", len(rows))
    c.stats["notificaciones recientes"] = unread


# ── orchestration ─────────────────────────────────────────────────────────────────────────
def seed_tenant(session, slug: str, legal_name: str, tax_id: str, location: str) -> None:
    print(f"Tenant: {slug}")
    tenant = get_or_create_tenant(session, slug, legal_name, tax_id, location)
    staff = seed_staff(session, tenant)
    insurer_ids = seed_insurers(session, tenant.id)
    has_activity = session.query(AppointmentModel).filter(
        AppointmentModel.tenant_id == tenant.id.value).first()
    if has_activity:
        print("    ya tiene actividad, omitido (usa --reset para regenerar)")
        return
    tz = ZoneInfo(tenant.timezone)
    now = datetime.now(tz).replace(tzinfo=None, second=0, microsecond=0)
    c = Clinic(
        session=session, tenant=tenant, clock=SimClock(tz), now=now,
        admin=staff["admins"][0], second_admin=staff["admins"][1], doctors=staff["doctors"],
        specialty=staff["specialty"], nurse=staff["nurse"], reception=staff["reception"],
        insurer_ids=insurer_ids,
    )
    seed_patients(c)
    seed_vaccinations(c)
    seed_exceptions(c)
    seed_agenda(c)
    seed_amendments(c)
    seed_documents(c)
    seed_users(c)
    seed_logins(c)
    finish(c)
    print("    + " + ", ".join(f"{v} {k}" for k, v in c.stats.items()))


def reset_demo(session, slugs: list[str]) -> None:
    session.execute(delete(TenantModel).where(TenantModel.slug.in_(slugs)))
    session.commit()
    print(f"Reset: tenants {slugs} borrados (cascada)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="borra los tenants demo antes de sembrar")
    args = parser.parse_args()

    session = get_session()
    # Fictitious NITs in the Salvadoran format (municipality-birth-correlative-check).
    demo = [("clinica-demo", "Clínica Demo, S.A. de C.V.", "0614-150318-101-4",
             "San Salvador · Centro"),
            ("centro-norte", "Centro Médico Norte, S.A. de C.V.", "0511-020719-102-7",
             "Santa Tecla · Las Palmas")]
    if args.reset:
        reset_demo(session, [d[0] for d in demo])
    for slug, legal_name, tax_id, location in demo:
        seed_tenant(session, slug, legal_name, tax_id, location)
    session.close()
    print("\nListo. Contraseña de todos los usuarios demo:", PASSWORD)


if __name__ == "__main__":
    main()
