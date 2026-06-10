"""Builders that assemble domain entities and seed an in-memory store for use-case tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from medicore.application.common.context import ActorContext
from medicore.domain.entities.availability import (
    BookingRules,
    DoctorAvailability,
    WeeklyDay,
)
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.entities.tenant import Location, Tenant
from medicore.domain.entities.user import User
from medicore.domain.enums import Role, Sex, UserStatus
from medicore.domain.shared.identifiers import (
    AvailabilityId,
    LocationId,
    PatientId,
    PlatformAdminId,
    TenantId,
    UserId,
)
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.time_range import TimeRange
from tests.support.fakes import PlainPasswordHasher
from tests.support.unit_of_work import InMemoryUnitOfWorkFactory

PASSWORD = "s3cret-pass"


def build_tenant(slug: str = "clinica-norte") -> Tenant:
    tid = TenantId.new()
    return Tenant(
        id=tid,
        legal_name="Clínica Norte SL",
        tax_id="B12345678",
        slug=Slug(slug),
        timezone="Europe/Madrid",
        locations=[
            Location(id=LocationId.new(), tenant_id=tid, name="Madrid · Atocha", is_primary=True)
        ],
    )


def build_user(
    tenant_id: TenantId,
    role: Role,
    *,
    name: str | None = None,
    email: str | None = None,
    status: UserStatus = UserStatus.ACTIVE,
    password: str = PASSWORD,
) -> User:
    name = name or f"{role.value.title()} User"
    email = email or f"{role.value}@clinica-norte.test"
    return User(
        id=UserId.new(),
        tenant_id=tenant_id,
        name=name,
        email=email,
        password_hash=PlainPasswordHasher().hash(password),
        role=role,
        status=status,
        specialty="Cardiología" if role == Role.DOCTOR else None,
    )


def build_patient(tenant_id: TenantId, code: str = "P-00100", **overrides) -> Patient:
    defaults = {
        "id": PatientId.new(),
        "tenant_id": tenant_id,
        "code": code,
        "first_name": "Lucía",
        "last_name": "Fernández",
        "sex": Sex.FEMALE,
        "date_of_birth": date(1985, 4, 12),
    }
    defaults.update(overrides)
    return Patient(**defaults)


def build_weekday_availability(
    tenant_id: TenantId,
    doctor_id: UserId,
    *,
    slot_minutes: int = 30,
    min_advance_hours: int = 0,
) -> DoctorAvailability:
    """Mon–Fri 09:00–13:00 availability with permissive booking rules."""
    weekly = [WeeklyDay(day_of_week=d) for d in range(7)]
    for d in range(5):  # Monday..Friday
        weekly[d] = WeeklyDay(
            day_of_week=d, enabled=True, blocks=[TimeRange(time(9, 0), time(13, 0))]
        )
    return DoctorAvailability(
        id=AvailabilityId.new(),
        tenant_id=tenant_id,
        doctor_id=doctor_id,
        weekly=weekly,
        rules=BookingRules(
            slot_minutes=slot_minutes,
            min_advance_hours=min_advance_hours,
            allow_same_day=True,
        ),
    )


@dataclass
class Seed:
    """A ready-to-use clinic with a tenant, staff, a patient, availability and a UoW factory."""

    factory: InMemoryUnitOfWorkFactory
    tenant: Tenant
    admin: User
    doctor: User
    nurse: User
    receptionist: User
    patient: Patient
    availability: DoctorAvailability
    platform_admin: PlatformAdmin

    def actor(self, user: User) -> ActorContext:
        return ActorContext(user_id=user.id, tenant_id=self.tenant.id, role=user.role)

    @property
    def doctor_actor(self) -> ActorContext:
        return self.actor(self.doctor)

    @property
    def receptionist_actor(self) -> ActorContext:
        return self.actor(self.receptionist)


def seed_clinic() -> Seed:
    factory = InMemoryUnitOfWorkFactory()
    tenant = build_tenant()
    admin = build_user(tenant.id, Role.ADMIN)
    doctor = build_user(
        tenant.id, Role.DOCTOR, name="Dra. Elena Ruiz", email="elena@clinica-norte.test"
    )
    nurse = build_user(tenant.id, Role.NURSE)
    receptionist = build_user(tenant.id, Role.RECEPTIONIST)
    patient = build_patient(tenant.id, primary_doctor_id=doctor.id)
    availability = build_weekday_availability(tenant.id, doctor.id)
    platform_admin = PlatformAdmin(
        id=PlatformAdminId.new(),
        name="Super Admin",
        email="super@medicore.health",
        password_hash=PlainPasswordHasher().hash(PASSWORD),
    )

    store = factory.store
    store.tenants[tenant.id.value] = tenant
    for user in (admin, doctor, nurse, receptionist):
        store.users[user.id.value] = user
    store.patients[patient.id.value] = patient
    store.availability[availability.id.value] = availability
    store.platform_admins[platform_admin.id.value] = platform_admin

    return Seed(
        factory=factory,
        tenant=tenant,
        admin=admin,
        doctor=doctor,
        nurse=nurse,
        receptionist=receptionist,
        patient=patient,
        availability=availability,
        platform_admin=platform_admin,
    )
