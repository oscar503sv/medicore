"""Seed rich, up-to-date demo data by replaying the clinic's history through the real use cases.

Per tenant: 2 admins, 5 doctors (each with a specialty and working hours), 1 nurse,
1 receptionist, 5 Salvadoran insurers and ~70 patients (some children and babies for
pediatrics, a few registered this week) with their vaccination histories (El Salvador's
national scheme), in-clinic applications (ordered at consultations or walk-ins with an
outside prescription) and minor procedures (catalog, orders from consultations, nursing
walk-ins, today's procedure appointments, consent, notes, specimens). Everything is
relative to the day the script runs:

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

Demo users get the password from ``DEMO_PASSWORD`` (``demo1234`` in development when unset)
and the clinic admins the one from ``DEMO_ADMIN_PASSWORD`` (``DEMO_PASSWORD`` when unset). In
production both are required: the script refuses the public default and a shared admin password.

Usage:
    .venv/bin/python scripts/seed_demo.py [--reset]
"""

from __future__ import annotations

import argparse
import os
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import ApplicationError
from medicore.application.use_cases.applications import (
    CancelApplicationOrder,
    CloseObservation,
    CreateExternalOrder,
    CreateExternalOrderCommand,
    RecordApplication,
    RecordApplicationCommand,
    VoidApplication,
)
from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    CreateAppointmentCommand,
    MarkNoShow,
    RescheduleAppointment,
)
from medicore.application.use_cases.availability import AddAvailabilityException
from medicore.application.use_cases.certificates import (
    IssueCertificateCommand,
    IssueMedicalCertificate,
)
from medicore.application.use_cases.consultations import (
    AddApplicationDraft,
    AddDiagnosis,
    AddExam,
    AddPrescriptionDraft,
    AddProcedureDraft,
    AutosaveConsultation,
    ConsultationPatch,
    SignConsultation,
    SignConsultationCommand,
    StartConsultation,
)
from medicore.application.use_cases.fees import AdjustAppointmentFee, UpdateDoctorFees
from medicore.application.use_cases.monitoring import RecordJobRun
from medicore.application.use_cases.patients import CreatePatient, CreatePatientCommand
from medicore.application.use_cases.procedures import (
    AmendProcedure,
    CancelProcedure,
    CreateProcedure,
    CreateProcedureCommand,
    CreateProcedureType,
    GetProcedureCatalog,
    ProcedureTypeCommand,
    RecordProcedureConsent,
    SaveProcedureProgress,
    SetProcedureTypeActive,
    SignProcedure,
    UpdateProcedureType,
)
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
from medicore.domain.entities.application import ApplicationDraft, ApplicationOrder
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
from medicore.domain.entities.procedure import Procedure, ProcedureProgress, ProcedureType
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import (
    CLINICAL_MODULES,
    AddonModule,
    ApplicationOrderSource,
    ApplicationOutcome,
    ApplicationRoute,
    ApplicationSite,
    AppointmentType,
    AvailabilityExceptionKind,
    CertificateKind,
    DocumentKind,
    ExamKind,
    InjectionSite,
    PracticeModel,
    PrescriptionStatus,
    ProcedurePerformer,
    Role,
    Sex,
    UserStatus,
    VaccinationOutcome,
    VaccinationSource,
    VaccineRoute,
)
from medicore.domain.services.allergies import allergy_conflicts
from medicore.domain.services.immunization import (
    SCHEDULE,
    VACCINES,
    ScheduledDose,
    add_months,
    applies_to,
)
from medicore.domain.services.plan_catalog import CLINICA, CLINICA_PLUS
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
from medicore.domain.value_objects.exam_request import ExamRequest
from medicore.domain.value_objects.fee import fee
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.soap_note import SoapNote
from medicore.domain.value_objects.subscription import Subscription
from medicore.domain.value_objects.time_range import TimeRange
from medicore.domain.value_objects.user_preferences import UserPreferences
from medicore.domain.value_objects.vitals import Vitals
from medicore.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from medicore.infrastructure.auth.code_generator import DbSequentialCodeGenerator
from medicore.infrastructure.auth.system_clock import SystemClock
from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.engine import get_session, get_session_factory
from medicore.infrastructure.persistence.models.appointment import AppointmentModel
from medicore.infrastructure.persistence.models.notification import NotificationModel
from medicore.infrastructure.persistence.models.tenant import TenantModel
from medicore.infrastructure.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
    SqlAlchemyUnitOfWorkFactory,
)

# Password for every demo user. Override with DEMO_PASSWORD (mandatory in production, where
# the public default would let anyone log in to a publicly reachable demo). The clinic admins
# get DEMO_ADMIN_PASSWORD instead (also mandatory in production), so the shared demo password
# never opens the administration of a clinic.
_DEFAULT_DEMO_PASSWORD = "demo1234"
PASSWORD = os.environ.get("DEMO_PASSWORD", "").strip() or _DEFAULT_DEMO_PASSWORD
ADMIN_PASSWORD = os.environ.get("DEMO_ADMIN_PASSWORD", "").strip() or PASSWORD
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
        ("Marta Ayala", "marta.ayala", Role.NURSE, None, True),
        ("Jorge Pleitez", "jorge.pleitez", Role.RECEPTIONIST, None, True),
        ("Carolina Guevara", "carolina.guevara", Role.ADMIN, None, True),
    ],
}
# A user invited a few days ago by the second admin (as nurse, then corrected to reception).
# Centro Norte has no free support seat on its plan, so nobody is invited there.
INVITED = {
    "clinica-demo": ("Andrea Molina", "andrea.molina"),
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


# In-clinic applications: (drug, dose, route, doses, interval h, observation min, instructions).
IM, IV = ApplicationRoute.INTRAMUSCULAR, ApplicationRoute.INTRAVENOUS
NEB = ApplicationRoute.NEBULIZED
APPLICATIONS = [
    ("Diclofenaco sódico", "75 mg", IM, 1, None, 30, None),
    ("Ketorolaco", "30 mg", IM, 1, None, 30, None),
    ("Dexametasona", "8 mg", IM, 1, None, 30, None),
    ("Metoclopramida", "10 mg", IM, 1, None, 30, "Si persiste el vómito, avisar al médico."),
    ("Ceftriaxona", "1 g", IM, 3, 24, 30, "Diluir en lidocaína 1 %. Una dosis diaria."),
    ("Penicilina benzatínica", "1 200 000 UI", IM, 1, None, 60, None),
    ("Salbutamol", "2.5 mg", NEB, 3, 1, 15, "Con 3 ml de solución salina, cada 20–60 min."),
    ("Complejo B", "3 ml", IM, 3, 48, 15, None),
    ("Hidratación: solución Hartmann", "1 000 ml", IV, 1, None, 30, "Pasar en 2 horas."),
]
EXTERNAL_PRESCRIBERS = [
    ("Dr. Ernesto Alfaro Mejía", "8412"),
    ("Dra. Gabriela Rivas de Henríquez", "11235"),
    ("Dr. Mauricio Cañas Flores", "6027"),
    ("Dra. Karla Portillo Ayala", "15390"),
]


# Procedures ordered at the consultation, by specialty: (catalog name, indication).
# Each doctor's fees (USD): consultation, follow-up, check-up, emergency (None: not offered).
FEES_BY_SPECIALTY: dict[str, tuple[int, int, int, int | None]] = {
    "Medicina General": (25, 15, 20, 35),
    "Cardiología": (45, 30, 40, 60),
    "Pediatría": (30, 20, 25, 40),
    "Dermatología": (40, 25, 35, None),
    "Ginecología": (40, 25, 35, 55),
    "Traumatología": (45, 30, 40, 60),
    "Endocrinología": (45, 30, 40, None),
}
FEE_TYPES = (AppointmentType.CONSULT, AppointmentType.FOLLOW_UP, AppointmentType.CHECK_UP,
             AppointmentType.EMERGENCY)
# Catalog prices (USD); a procedure left out has no fixed price.
PROCEDURE_PRICES: dict[str, int] = {
    "Curación de herida": 15, "Sutura de herida": 35, "Retiro de puntos": 10,
    "Drenaje de absceso": 40, "Extracción de uña (onicectomía)": 50, "Lavado de oído": 20,
    "Infiltración articular": 45, "Crioterapia de lesión cutánea": 35,
    "Colocación de DIU": 60, "Citología cervicovaginal (Papanicolaou)": 25,
    "Electrocardiograma": 25, "Biopsia de piel": 60, "Retiro de cuerpo extraño": 30,
    "Taponamiento nasal anterior": 30,
}
FEE_DISCOUNTS = ["Adulto mayor", "Cortesía", "Paciente frecuente", "Descuento por convenio"]

# Exams a doctor of each specialty usually orders (name, kind, notes).
EXAM_ORDERS = {
    "Medicina General": [
        ("Hemograma completo", ExamKind.LAB, None),
        ("Glucosa en ayunas", ExamKind.LAB, "Ayuno de 8 horas"),
        ("Examen general de orina", ExamKind.LAB, None),
        ("Examen general de heces", ExamKind.LAB, None),
        ("Perfil lipídico", ExamKind.LAB, "Ayuno de 12 horas"),
        ("Radiografía de tórax", ExamKind.IMAGING, "PA y lateral"),
    ],
    "Cardiología": [
        ("Perfil lipídico", ExamKind.LAB, "Ayuno de 12 horas"),
        ("Electrocardiograma", ExamKind.OTHER, None),
        ("Ecocardiograma", ExamKind.IMAGING, None),
        ("Creatinina sérica", ExamKind.LAB, None),
    ],
    "Pediatría": [
        ("Hemograma completo", ExamKind.LAB, None),
        ("Examen general de orina", ExamKind.LAB, None),
        ("Examen general de heces", ExamKind.LAB, None),
    ],
    "Dermatología": [
        ("Examen micológico directo (KOH)", ExamKind.LAB, None),
        ("Hemograma completo", ExamKind.LAB, None),
    ],
    "Ginecología": [
        ("Ultrasonografía pélvica", ExamKind.IMAGING, "Con vejiga llena"),
        ("Ultrasonografía transvaginal", ExamKind.IMAGING, None),
        ("Prueba de embarazo (β-hCG)", ExamKind.LAB, None),
        ("Citología cervicovaginal", ExamKind.LAB, None),
        ("Mamografía", ExamKind.IMAGING, "Bilateral"),
    ],
    "Traumatología": [
        ("Radiografía de rodilla", ExamKind.IMAGING, "AP y lateral"),
        ("Radiografía de columna lumbar", ExamKind.IMAGING, None),
        ("Resonancia magnética", ExamKind.IMAGING, None),
    ],
    "Endocrinología": [
        ("Perfil tiroideo (TSH, T4 libre)", ExamKind.LAB, None),
        ("Hemoglobina glicosilada (HbA1c)", ExamKind.LAB, None),
        ("Glucosa en ayunas", ExamKind.LAB, "Ayuno de 8 horas"),
    ],
}

PROCEDURE_ORDERS = {
    "Medicina General": [
        ("Sutura de herida", "Herida cortante de 3 cm en antebrazo izquierdo"),
        ("Curación de herida", "Herida en pierna derecha en proceso de cicatrización"),
        ("Drenaje de absceso", "Absceso fluctuante en región axilar derecha"),
        ("Lavado de oído", "Tapón de cerumen en oído derecho"),
        ("Retiro de cuerpo extraño", "Astilla en palma de mano derecha"),
        ("Extracción de uña (onicectomía)", "Uña encarnada recurrente en primer dedo del pie"),
    ],
    "Dermatología": [
        ("Biopsia de piel", "Lesión pigmentada de bordes irregulares en espalda"),
        ("Crioterapia de lesión cutánea", "Verruga vulgar en dorso de mano"),
    ],
    "Ginecología": [
        ("Colocación de DIU", "Planificación familiar: desea un método de larga duración"),
        ("Citología cervicovaginal (Papanicolaou)", "Tamizaje de rutina"),
    ],
    "Cardiología": [("Electrocardiograma", "Palpitaciones; control del ritmo")],
    "Traumatología": [("Infiltración articular", "Gonalgia crónica por artrosis de rodilla")],
    "Pediatría": [("Lavado de oído", "Tapón de cerumen bilateral")],
}
# What the note says per procedure: (anesthesia, findings, materials, specimen).
PROCEDURE_NOTES = {
    "Sutura de herida": ("Lidocaína 2 %, 4 ml, infiltración local",
                         "Herida limpia de bordes regulares, sin compromiso tendinoso",
                         "Nylon 4-0, gasas, apósito", None),
    "Curación de herida": (None, "Tejido de granulación sano, sin signos de infección",
                           "Solución salina, gasas, apósito", None),
    "Drenaje de absceso": ("Lidocaína 2 %, 5 ml, infiltración local",
                           "Salida de material purulento de 8 ml aprox.",
                           "Hoja de bisturí n.º 11, gasa yodoformada", None),
    "Lavado de oído": (None, "Tapón de cerumen extraído completo; membrana timpánica íntegra",
                       "Jeringa de irrigación, agua tibia", None),
    "Retiro de cuerpo extraño": ("Lidocaína 2 %, 1 ml", "Astilla de madera de 6 mm extraída",
                                 "Pinza, aguja hipodérmica, apósito", None),
    "Extracción de uña (onicectomía)": ("Lidocaína 2 %, bloqueo digital",
                                        "Lámina ungueal encarnada en borde lateral",
                                        "Torniquete digital, pinza, apósito", None),
    "Biopsia de piel": ("Lidocaína 2 %, 2 ml, infiltración local",
                        "Lesión de 6 mm, pigmentación irregular",
                        "Sacabocado de 4 mm, nylon 4-0, frasco con formol",
                        "Piel de espalda, sacabocado de 4 mm, en formol al 10 %"),
    "Crioterapia de lesión cutánea": (None, "Verruga de 5 mm, dos ciclos de congelación",
                                      "Nitrógeno líquido", None),
    "Colocación de DIU": (None, "Histerometría de 7 cm; cuello sin lesiones",
                          "DIU T de cobre 380A, espéculo, histerómetro", None),
    "Citología cervicovaginal (Papanicolaou)": (
        None, "Cuello de aspecto sano", "Espéculo, espátula de Ayre, citocepillo",
        "Extendido cervicovaginal fijado, 2 láminas"),
    "Electrocardiograma": (None, "Ritmo sinusal, FC 74 lpm, sin alteraciones agudas",
                           "Electrodos desechables", None),
    "Infiltración articular": ("Lidocaína 1 %, 2 ml", "Rodilla sin derrame significativo",
                               "Metilprednisolona 40 mg, aguja 21G", None),
    "Retiro de puntos": (None, "Herida bien afrontada, sin signos de infección",
                         "Tijera de retiro, gasas", None),
}
WALK_IN_PROCEDURES = [
    ("Curación de herida", "Raspón en rodilla izquierda por caída en bicicleta"),
    ("Retiro de puntos", "Sutura en mano hecha hace 8 días en otro centro"),
    ("Lavado de oído", "Sensación de oído tapado desde hace una semana"),
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
    procedure_types: dict[str, ProcedureType] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def tid(self) -> TenantId:
        return self.tenant.id

    def has(self, module: AddonModule) -> bool:
        """The clinic contracted this optional module (no data is made for the others)."""
        return module in self.tenant.subscription.modules

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
        password_hash=HASHER.hash(ADMIN_PASSWORD if role == Role.ADMIN else PASSWORD),
        role=role, status=UserStatus.ACTIVE,
        sex=Sex.FEMALE if female else Sex.MALE, specialty=specialty,
        phone=f"7{RNG.randint(100, 999)}-{RNG.randint(1000, 9999)}",
        # Doctors sign prescriptions with their (fictitious) board number.
        jvpm=str(RNG.randint(10000, 29999)) if role == Role.DOCTOR else None,
        # A populated demo clinic needs no first-login checklist.
        preferences=UserPreferences(welcome_seen=True, onboarding_dismissed=True),
    )


# How each demo clinic's doctors work: Clínica Demo shows associated doctors (each sets their
# prices and sees their income), Centro Norte employed ones (the administration does).
DEMO_PRACTICE_MODELS = {
    "clinica-demo": PracticeModel.ASSOCIATED,
    "centro-norte": PracticeModel.EMPLOYED,
}

# The public demo clinics never expire. Clínica Demo shows every feature; Centro Norte shows
# a smaller plan (Clínica: 3 doctors, 3 support seats, per-user permissions) with one module,
# so the demo also shows locked modules, full seats and the clinic analytics tier (Clínica
# Plus already includes operations, so the analytics add-on is not sold to it).
DEMO_SUBSCRIPTIONS = {
    "clinica-demo": Subscription(plan_code=CLINICA_PLUS, modules=CLINICAL_MODULES),
    "centro-norte": Subscription(
        plan_code=CLINICA, modules=frozenset({AddonModule.VACCINATION})
    ),
}


def get_or_create_tenant(
    session, slug: str, legal_name: str, tax_id: str, location: str
) -> Tenant:
    row = session.query(TenantModel).filter(TenantModel.slug == slug).first()
    if row:
        print(f"  tenant '{slug}' ya existe")
        tid = TenantId.parse(row.id)
        uow = SqlAlchemyUnitOfWork(session, tid)
        with uow:
            tenant = uow.tenants.get_by_id(tid)
            if tenant.subscription != DEMO_SUBSCRIPTIONS[slug]:
                tenant.subscription = DEMO_SUBSCRIPTIONS[slug]
                uow.tenants.save(tenant)
                uow.commit()
        return tenant
    tid = TenantId.new()
    tenant = Tenant(
        id=tid, legal_name=legal_name, tax_id=tax_id, slug=Slug(slug), timezone=TIMEZONE,
        subscription=DEMO_SUBSCRIPTIONS[slug], practice_model=DEMO_PRACTICE_MODELS[slug],
        locations=[Location(id=LocationId.new(), tenant_id=tid, name=location, is_primary=True,
                            phone=f"2{RNG.randint(200, 299)}-{RNG.randint(1000, 9999)}")],
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
        on = min(on, at.date())  # right after midnight "latest" is still yesterday
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
    item = RNG.choice(APPLICATIONS)
    # A doctor rarely orders what the patient is allergic to (one case shows the override).
    clash = allergy_conflicts(item[0], patient.allergies) and RNG.random() < 0.85
    if c.has(AddonModule.APPLICATIONS) and RNG.random() < 0.09 and not clash:
        drug, dose, route, n, every, obs, notes = item
        AddApplicationDraft(c.uow(), c.at(start + timedelta(minutes=15))).execute(
            me, consultation.id,
            ApplicationDraft(drug=drug, dose=dose, route=route, doses_total=n,
                             interval_hours=every, observation_minutes=obs, instructions=notes),
        )
    exams = EXAM_ORDERS.get(c.specialty[doctor.id], EXAM_ORDERS["Medicina General"])
    if RNG.random() < 0.3:
        for name, kind, notes in RNG.sample(exams, min(len(exams), RNG.choice([1, 1, 2, 3]))):
            AddExam(c.uow(), c.at(start + timedelta(minutes=15))).execute(
                me, consultation.id, ExamRequest(name=name, kind=kind, notes=notes))
        c.count("órdenes de exámenes")
    orders = PROCEDURE_ORDERS.get(c.specialty[doctor.id])
    if orders and c.has(AddonModule.PROCEDURES) and RNG.random() < 0.12:
        name, indication = RNG.choice(orders)
        # Now and then the procedure goes inside the consultation fee.
        AddProcedureDraft(c.uow(), c.at(start + timedelta(minutes=16))).execute(
            me, consultation.id, c.procedure_types[name].id, indication,
            included=RNG.random() < 0.25)
    record = SignConsultation(c.uow(), c.codes(),
                              c.at(start + timedelta(minutes=RNG.randint(18, 27)))).execute(
        me, SignConsultationCommand(consultation_id=consultation.id))
    c.signed.append(record)
    c.count("consultas firmadas")
    if RNG.random() < 0.06:  # a rest or attendance certificate for work or school
        rest = RNG.random() < 0.7
        IssueMedicalCertificate(c.uow(), c.codes(), c.at(start + timedelta(minutes=28))).execute(
            me, IssueCertificateCommand(
                record_id=record.id,
                kind=CertificateKind.REST if rest else CertificateKind.ATTENDANCE,
                rest_from=start.date() if rest else None,
                rest_days=RNG.choice([1, 2, 3, 3, 5]) if rest else None,
                include_diagnosis=RNG.random() < 0.4,
                addressee=RNG.choice([None, "Recursos Humanos", "Dirección del centro escolar"])))
        c.count("constancias médicas")
    if appt.charge.listed is not None and RNG.random() < 0.08:
        listed = appt.charge.listed.amount
        AdjustAppointmentFee(c.uow(), c.at(start + timedelta(minutes=30))).execute(
            pricing_actor(c, doctor), appt.id,
            fee(0 if RNG.random() < 0.3 else listed * Decimal("0.8")), RNG.choice(FEE_DISCOUNTS))
        c.count("cobros ajustados")
    reopened = start + timedelta(days=RNG.randint(1, 6), hours=2)
    if RNG.random() < 0.3 and reopened < c.now:  # reopened later (audited as record.viewed)
        GetMedicalRecord(c.uow(), c.at(reopened)).execute(me, record.id)


def pricing_actor(c: Clinic, doctor: User) -> ActorContext:
    """Who sets prices and adjusts charges: each doctor with associated doctors, the
    administration with employed ones."""
    employed = c.tenant.practice_model == PracticeModel.EMPLOYED
    return actor(c, c.admin if employed else doctor)


def seed_fees(c: Clinic) -> None:
    """The fees are set before the agenda starts (by each doctor or by the admin, per the
    clinic's practice model)."""
    at = datetime.combine(c.today - timedelta(weeks=PAST_WEEKS, days=4), time(8, 30))
    for doctor in c.doctors:
        prices = FEES_BY_SPECIALTY[c.specialty[doctor.id]]
        UpdateDoctorFees(c.uow(), c.at(at)).execute(pricing_actor(c, doctor), doctor.id, {
            kind: fee(amount) for kind, amount in zip(FEE_TYPES, prices, strict=True)
            if amount is not None
        })
    c.count("tarifas", len(c.doctors))


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


# ── in-clinic applications ────────────────────────────────────────────────────────────────
def _site(route: ApplicationRoute) -> ApplicationSite | None:
    if route == ApplicationRoute.INTRAMUSCULAR:
        return RNG.choice([ApplicationSite.LEFT_GLUTEUS, ApplicationSite.RIGHT_GLUTEUS,
                           ApplicationSite.LEFT_ARM, ApplicationSite.RIGHT_ARM])
    if route == ApplicationRoute.INTRAVENOUS:
        return RNG.choice([ApplicationSite.LEFT_HAND, ApplicationSite.RIGHT_HAND,
                           ApplicationSite.LEFT_FOREARM])
    return None


def seed_applications(c: Clinic) -> None:
    """Orders issued at signing (drafted in ``attend``) plus walk-ins with an outside
    prescription, then the nurse applying every dose already due: observation closed without
    reaction, except a mild reaction, a refused dose, an allergy override and a voided entry.
    Today some doses are still to apply and one patient is under observation right now."""
    nurse = actor(c, c.nurse)
    latest = c.now - timedelta(minutes=2)

    def external(patient: Patient, when: datetime, item, prescriber=None):
        drug, dose, route, n, every, obs, notes = item
        name, jvpm = prescriber or RNG.choice(EXTERNAL_PRESCRIBERS)
        c.count("aplicaciones: órdenes externas")
        return CreateExternalOrder(c.uow(), c.at(when)).execute(nurse, CreateExternalOrderCommand(
            patient_id=patient.id, drug=drug, dose=dose, route=route, prescriber=name,
            jvpm=jvpm, doses_total=n, interval_hours=every, observation_minutes=obs,
            instructions=notes))

    def apply(order: ApplicationOrder, patient: Patient, at: datetime, *,
              outcome=ApplicationOutcome.APPLIED, notes=None, override=None, close=True,
              reaction=None):
        applied = outcome == ApplicationOutcome.APPLIED
        rec = RecordApplication(c.uow(), c.at(at)).execute(nurse, RecordApplicationCommand(
            order_id=order.id, outcome=outcome,
            lot=f"L{RNG.randint(10000, 99999)}" if applied else None,
            lot_expiry=date(c.today.year + 1, RNG.randint(1, 12), 1) if applied else None,
            site=_site(order.route) if applied else None,
            blood_pressure=f"{RNG.randint(105, 135)}/{RNG.randint(65, 85)}" if applied else None,
            temperature=round(RNG.uniform(36.2, 37.4), 1) if applied else None,
            allergy_override=override, notes=notes))
        c.count("aplicaciones registradas")
        if applied and close and order.observation_minutes:
            end = at + timedelta(minutes=order.observation_minutes + RNG.randint(0, 6))
            if end <= latest:
                CloseObservation(c.uow(), c.at(end)).execute(
                    nurse, rec.id, reaction is not None, reaction)
        return rec

    # Walk-ins with an outside prescription over the last weeks.
    adults = [p for p in c.patients if _months(p.date_of_birth, c.today) >= 18 * 12]
    for _ in range(6):
        day = c.today - timedelta(days=RNG.randint(1, 20))
        when = datetime.combine(day, time(RNG.randint(8, 15), RNG.choice([0, 20, 40])))
        external(RNG.choice(adults), when, RNG.choice(APPLICATIONS))

    # A 3-day ceftriaxone that started yesterday: today's dose is due, tomorrow's pending.
    ceftriaxone = next(a for a in APPLICATIONS if a[0] == "Ceftriaxona")
    morning = c.now.replace(hour=8, minute=0)
    if morning > latest:
        morning = c.now - timedelta(hours=1)
    cef = RNG.choice([p for p in adults if not allergy_conflicts("Ceftriaxona", p.allergies)])
    external(cef, morning - timedelta(days=1), ceftriaxone)

    # Play out every open order: each dose due long enough ago was applied.
    by_id = {p.id: p for p in c.patients}
    uow = c.uow()
    with uow:
        orders = uow.applications.list_open_orders()
    orders.sort(key=lambda o: o.starts_at)
    reacted = refused = overridden = voided = False
    for order in orders:
        patient = by_id[order.patient_id]
        clash = allergy_conflicts(order.drug, patient.allergies)
        for n in range(1, order.doses_total + 1):
            due = order.due_at(n)
            at = due + timedelta(minutes=RNG.randint(4, 25))
            if due >= morning.replace(hour=0) + timedelta(days=1) or at > latest:
                break  # still due (today's are on the worklist)
            if clash:
                if overridden:
                    CancelApplicationOrder(c.uow(), c.at(at)).execute(
                        nurse, order.id, f"Alergia a {', '.join(clash)}: se consultó al médico")
                    c.count("aplicaciones: órdenes canceladas")
                    break
                apply(order, patient, at, override="Indicación confirmada por el médico tratante"
                      "; reacción previa leve, se aplica con observación prolongada.")
                overridden = True
                continue
            if not refused and n == 1 and order.doses_total == 1 and RNG.random() < 0.15:
                apply(order, patient, at, outcome=ApplicationOutcome.REFUSED,
                      notes="El paciente prefiere tomar el medicamento por vía oral.")
                refused = True
                break
            recent = due.date() >= c.today - timedelta(days=10)
            if not reacted and recent and order.source == ApplicationOrderSource.INTERNAL:
                apply(order, patient, at, reaction="Eritema y prurito en el sitio de aplicación; "
                      "cedió con compresas frías. Se indicó vigilancia en casa.")
                reacted = True
                continue
            if not voided and order.route == IM and n == 1 and RNG.random() < 0.2:
                wrong = apply(order, patient, at, close=False)
                VoidApplication(c.uow(), c.at(at + timedelta(minutes=3))).execute(
                    nurse, wrong.id, "Lote mal digitado")
                c.count("aplicaciones anuladas")
                voided = True
                at += timedelta(minutes=5)
            apply(order, patient, at)

    # Right now: one patient under observation, another one waiting.
    rest = [p for p in adults if p.id != cef.id and not p.allergies]
    ketorolaco = next(a for a in APPLICATIONS if a[0] == "Ketorolaco")
    watching = external(rest[0], c.now - timedelta(minutes=14), ketorolaco)
    apply(watching, rest[0], c.now - timedelta(minutes=10))
    dexa = next(a for a in APPLICATIONS if a[0] == "Dexametasona")
    external(rest[1], c.now - timedelta(minutes=6), dexa)


# ── procedures ────────────────────────────────────────────────────────────────────────────
def seed_procedure_catalog(c: Clinic) -> None:
    """The preloaded catalog, plus one procedure the clinic added and one it archived."""
    admin = actor(c, c.admin)
    start = datetime.combine(c.today - timedelta(weeks=PAST_WEEKS, days=3), time(9, 0))
    types = GetProcedureCatalog(c.uow(), c.at(start)).execute(admin)
    CreateProcedureType(c.uow(), c.at(start + timedelta(minutes=20))).execute(
        admin, ProcedureTypeCommand(
            name="Taponamiento nasal anterior", performer=ProcedurePerformer.DOCTOR,
            follow_up_days=2,
            technique_template="Compresión digital previa. Colocación de tapón anterior con "
                               "gasa vaselinada en la fosa nasal sangrante.",
            instructions_template="No sonarse la nariz. Retiro del tapón en 48 horas.",
        ))
    retiro_diu = next(t for t in types if t.name == "Retiro de DIU")
    SetProcedureTypeActive(c.uow(), c.at(start + timedelta(minutes=25))).execute(
        admin, retiro_diu.id, False)
    for kind in GetProcedureCatalog(c.uow(), c.at(start + timedelta(minutes=26))).execute(admin):
        if kind.name in PROCEDURE_PRICES:
            UpdateProcedureType(c.uow(), c.at(start + timedelta(minutes=27))).execute(
                admin, kind.id, ProcedureTypeCommand(
                    name=kind.name, performer=kind.performer,
                    requires_consent=kind.requires_consent, follow_up_days=kind.follow_up_days,
                    takes_specimen=kind.takes_specimen,
                    technique_template=kind.technique_template,
                    instructions_template=kind.instructions_template,
                    price=fee(PROCEDURE_PRICES[kind.name]),
                ))
    c.procedure_types = {t.name: t for t in GetProcedureCatalog(
        c.uow(), c.at(start + timedelta(minutes=30))).execute(admin)}


def _perform(c: Clinic, p: Procedure, patient: Patient, user: User, at: datetime,
             *, override: str | None = None) -> Procedure:
    """Consent (if needed), checklist, vitals and note, then sign — like in the app."""
    me = actor(c, user)
    kind = next(t for t in c.procedure_types.values() if t.id == p.type_id)
    anesthesia, findings, materials, specimen = PROCEDURE_NOTES.get(
        p.type_name, (None, None, None, None))
    adult = patient.age(at.date()) >= 14
    if p.requires_consent:
        signer, relationship = (patient.full_name, None) if adult else (
            f"{RNG.choice(['María', 'Ana', 'Rosa', 'Carmen'])} {patient.last_name}", "Madre")
        witness = c.nurse if user.id != c.nurse.id else c.reception
        RecordProcedureConsent(c.uow(), c.at(at)).execute(
            me, p.id, signer, relationship, witness.name)
    bp = (lambda: f"{RNG.randint(108, 138)}/{RNG.randint(66, 88)}") if adult else (lambda: None)
    progress = ProcedureProgress(
        allergies_reviewed=True, anticoagulants=False if adult else None, fasting=None,
        allergy_override=override,
        bp_before=bp(), hr_before=RNG.randint(64, 96), spo2_before=RNG.randint(96, 99),
        temp_before=round(RNG.uniform(36.2, 37.1), 1),
        bp_after=bp(), hr_after=RNG.randint(62, 92), spo2_after=RNG.randint(96, 99),
        anesthesia=anesthesia, technique=kind.technique_template or p.type_name,
        findings=findings, materials=materials, complications="Ninguna",
        instructions=kind.instructions_template,
        specimen_sent=specimen is not None and p.takes_specimen,
        specimen_description=specimen if p.takes_specimen else None,
    )
    SaveProcedureProgress(c.uow(), c.at(at + timedelta(minutes=4))).execute(me, p.id, progress)
    done = SignProcedure(c.uow(), c.at(at + timedelta(minutes=RNG.randint(15, 30)))).execute(
        me, p.id)
    c.count("procedimientos realizados")
    return done


def seed_procedures(c: Clinic) -> None:
    """Play out what was ordered at consultations (by the doctor, or by nursing when the
    catalog allows), a few walk-ins registered by nursing, one cancellation and one
    amendment. Orders from the last two days stay pending on the worklist."""
    tz = c.clock.tz
    latest = c.now - timedelta(minutes=40)
    by_id = {p.id: p for p in c.patients}
    doctors = {d.id: d for d in c.doctors}
    nurse = actor(c, c.nurse)

    adults = [p for p in c.patients if p.age(c.today) >= 14]
    for name, indication in WALK_IN_PROCEDURES * 2:
        day = c.today - timedelta(days=RNG.randint(2, 30))
        when = datetime.combine(day, time(RNG.randint(8, 15), RNG.choice([0, 20, 40])))
        patient = RNG.choice(adults)
        p = CreateProcedure(c.uow(), c.at(when)).execute(nurse, CreateProcedureCommand(
            patient_id=patient.id, type_id=c.procedure_types[name].id, indication=indication))
        c.count("procedimientos directos")
        _perform(c, p, patient, c.nurse, when + timedelta(minutes=5))

    uow = c.uow()
    with uow:
        ordered = [p for p in uow.procedures.list_open()
                   if p.source.value == "consultation"]
    ordered.sort(key=lambda p: p.created_at)
    cancelled = overridden = False
    performed: list[tuple[Procedure, User]] = []
    for p in ordered:
        created = p.created_at.astimezone(tz).replace(tzinfo=None)
        if created.date() >= c.today - timedelta(days=2):
            continue  # recent orders: still pending
        doctor = doctors[p.ordered_by_id]
        patient = by_id[p.patient_id]
        if not cancelled and RNG.random() < 0.15:
            CancelProcedure(c.uow(), c.at(created + timedelta(hours=RNG.randint(1, 30)))).execute(
                actor(c, doctor), p.id, "El paciente prefiere realizarlo más adelante.")
            c.count("procedimientos cancelados")
            cancelled = True
            continue
        if RNG.random() < 0.6:
            at = created + timedelta(minutes=RNG.randint(10, 40))
        else:
            day = created.date() + timedelta(days=RNG.randint(1, 3))
            at = datetime.combine(day, time(RNG.randint(8, 15), RNG.choice([0, 30])))
        if at > latest:
            continue
        nursing = p.performer == ProcedurePerformer.DOCTOR_OR_NURSE and RNG.random() < 0.7
        user = c.nurse if nursing else doctor
        override = None
        anesthesia = PROCEDURE_NOTES.get(p.type_name, (None,))[0]
        if anesthesia and allergy_conflicts(anesthesia, patient.allergies):
            if overridden:
                continue
            override = "Alergia referida a otro anestésico; prueba intradérmica previa negativa."
            overridden = True
        performed.append((_perform(c, p, patient, user, at, override=override), user))

    # A doctor corrects a signed note.
    for p, user in reversed(performed):
        if user.role == Role.DOCTOR and p.performed_at is not None:
            when = p.performed_at.astimezone(tz).replace(tzinfo=None) + timedelta(hours=3)
            if when < latest:
                AmendProcedure(c.uow(), c.at(when)).execute(
                    actor(c, user), p.id, "Se aplicaron 4 ml de anestesia, no 2 ml.",
                    "Dato de anestesia corregido")
                c.count("procedimientos enmendados")
                break


def seed_procedure_appointments(c: Clinic) -> None:
    """Today's procedure appointments: two already done (one by nursing) and one later."""
    rec = actor(c, c.reception)
    general = next((d for d in c.doctors if c.specialty[d.id] == "Medicina General"), None)
    derma = next((d for d in c.doctors if c.specialty[d.id] == "Dermatología"), None)
    plan = [(general, "Retiro de puntos", "Retiro de puntos de sutura en antebrazo", c.nurse, True),
            (derma, "Crioterapia de lesión cutánea", "Crioterapia de verruga", None, True),
            (general, "Curación de herida", "Curación de herida en pie", None, False)]
    adults = [p for p in c.patients if p.age(c.today) >= 14 and not p.allergies]
    RNG.shuffle(adults)
    for doctor, name, reason, performer, done in plan:
        if doctor is None:
            continue
        free = [s for s in day_slots(c, doctor, c.today) if (doctor.id, s) not in c.taken
                and ((s + timedelta(minutes=45) <= c.now) if done else s > c.now)]
        if not free:
            continue
        start = free[-1] if done else free[0]
        patient = adults.pop()
        booked = datetime.combine(c.today - timedelta(days=RNG.randint(1, 4)), time(10, 15))
        appt = CreateAppointment(c.uow(), c.codes(), c.at(booked)).execute(
            rec, CreateAppointmentCommand(
                patient_id=patient.id, doctor_id=doctor.id,
                location_id=c.tenant.primary_location.id, type=AppointmentType.PROCEDURE,
                scheduled_start=start, reason=reason, insurance_id=insurer_for(c, patient)))
        c.taken.add((doctor.id, start))
        c.count("citas de procedimiento")
        if not done:
            continue
        user = performer or doctor
        p = CreateProcedure(c.uow(), c.at(start + timedelta(minutes=2))).execute(
            actor(c, user), CreateProcedureCommand(
                patient_id=patient.id, type_id=c.procedure_types[name].id, indication=reason,
                appointment_id=appt.id))
        _perform(c, p, patient, user, start + timedelta(minutes=5))


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
    # Invited with a temporary password that meets the policy; demo users then share the
    # public demo password, like everyone else seeded.
    user = InviteUser(c.uow(), HASHER, c.at(c.now - timedelta(days=4, hours=3))).execute(
        second, InviteUserCommand(name=name, email=f"{local}@{c.tenant.slug}.test",
                                  role=Role.NURSE, password="Temporal-Seed-7429"))
    uow = c.uow()
    with uow:
        invited = uow.users.get_by_id(user.id)
        invited.set_temporary_password(HASHER.hash(PASSWORD))
        uow.users.save(invited)
        uow.commit()
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
    if c.has(AddonModule.VACCINATION):
        seed_vaccinations(c)
    seed_exceptions(c)
    seed_fees(c)
    if c.has(AddonModule.PROCEDURES):
        seed_procedure_catalog(c)
    seed_agenda(c)
    if c.has(AddonModule.PROCEDURES):
        seed_procedure_appointments(c)
    if c.has(AddonModule.APPLICATIONS):
        seed_applications(c)
    if c.has(AddonModule.PROCEDURES):
        seed_procedures(c)
    seed_amendments(c)
    seed_documents(c)
    if str(c.tenant.slug) in INVITED:
        seed_users(c)
    seed_logins(c)
    finish(c)
    print("    + " + ", ".join(f"{v} {k}" for k, v in c.stats.items()))


def reset_demo(session, slugs: list[str]) -> None:
    session.execute(delete(TenantModel).where(TenantModel.slug.in_(slugs)))
    session.commit()
    print(f"Reset: tenants {slugs} borrados (cascada)")


def _check_demo_password() -> None:
    if len(PASSWORD) < 8:
        raise SystemExit("DEMO_PASSWORD must be at least 8 characters")
    if len(ADMIN_PASSWORD) < 8:
        raise SystemExit("DEMO_ADMIN_PASSWORD must be at least 8 characters")
    if not get_settings().is_production:
        return
    if PASSWORD == _DEFAULT_DEMO_PASSWORD:
        raise SystemExit(
            "Refusing to seed in production with the public default password: "
            "set DEMO_PASSWORD to a strong, private value."
        )
    if ADMIN_PASSWORD == PASSWORD:
        raise SystemExit(
            "Refusing to seed in production with the shared demo password for the admins: "
            "set DEMO_ADMIN_PASSWORD to a different, private value."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="borra los tenants demo antes de sembrar")
    args = parser.parse_args()
    _check_demo_password()

    # Recorded for the console's Monitoring page: the nightly --reset is a scheduled task,
    # so a failed or missing run shows up there. Only the outcome, never data.
    job = "demo_reset" if args.reset else "demo_seed"
    clock = SystemClock()
    started = clock.now()
    jobs = RecordJobRun(SqlAlchemyUnitOfWorkFactory(get_session_factory()), clock)
    try:
        _seed(args.reset)
    except BaseException as exc:
        jobs.execute(job, started, ok=False, detail=type(exc).__name__)
        raise
    jobs.execute(job, started, ok=True, detail="clinica-demo, centro-norte")


def _seed(reset: bool) -> None:
    session = get_session()
    # Fictitious NITs in the Salvadoran format (municipality-birth-correlative-check).
    demo = [("clinica-demo", "Clínica Demo, S.A. de C.V.", "0614-150318-101-4",
             "San Salvador · Centro"),
            ("centro-norte", "Centro Médico Norte, S.A. de C.V.", "0511-020719-102-7",
             "Santa Tecla · Las Palmas")]
    if reset:
        reset_demo(session, [d[0] for d in demo])
    for slug, legal_name, tax_id, location in demo:
        seed_tenant(session, slug, legal_name, tax_id, location)
    session.close()
    if PASSWORD == ADMIN_PASSWORD == _DEFAULT_DEMO_PASSWORD:
        print("\nListo. Contraseña de todos los usuarios demo:", PASSWORD)
    else:
        print("\nListo. Contraseñas demo: DEMO_PASSWORD (usuarios) y DEMO_ADMIN_PASSWORD "
              "(admins de clínica)")


if __name__ == "__main__":
    main()
