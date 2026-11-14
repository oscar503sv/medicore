"""In-memory repository implementations backed by an :class:`InMemoryStore`.

Each repo is tenant-scoped (constructed with a ``tenant_id``) and filters accordingly, so the
fakes exercise the same multi-tenant contract the real ORM repos will honor in fase 3.
``TenantRepository`` is the exception: it is global.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from medicore.application.common.login_throttle import WINDOW_MINUTES, lockout_until
from medicore.domain.entities.appointment import Appointment
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.auth_session import AuthSession
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.entities.consultation import Consultation
from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.entities.fee_schedule import FeeSchedule
from medicore.domain.entities.job_run import JobRun
from medicore.domain.entities.medical_certificate import MedicalCertificate
from medicore.domain.entities.medical_document import MedicalDocument
from medicore.domain.entities.medical_record import MedicalRecord
from medicore.domain.entities.notification import Notification
from medicore.domain.entities.patient import Patient
from medicore.domain.entities.plan import AddonPricing, Plan
from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.entities.platform_audit_log import PlatformAuditLog
from medicore.domain.entities.prescription import Prescription
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import DoctorProfile, User
from medicore.domain.enums import (
    ApplicationOutcome,
    AppointmentStatus,
    ProcedureStatus,
    VaccinationOutcome,
    VaccinationSource,
)
from medicore.domain.repositories._support import (
    ActiveImpersonation,
    ApplicationReportRow,
    AppointmentFact,
    AppointmentReportRow,
    AuditFilter,
    ConnectionStats,
    ConsoleLogin,
    DatabaseStatus,
    ErrorGroup,
    GlobalAuditRow,
    JobSummary,
    LockedLogin,
    LoginPressure,
    Page,
    Paging,
    PatientFilter,
    ProcedureFact,
    ProcedureReportRow,
    RecordFilter,
    RequestStatsRow,
    TableSize,
    TenantFilter,
    UserFilter,
    VaccinationReportRow,
)
from medicore.domain.shared.identifiers import (
    AppointmentId,
    CertificateId,
    ConsultationId,
    DocumentId,
    NotificationId,
    PatientId,
    PlatformAdminId,
    PrescriptionId,
    RecordId,
    SessionId,
    TenantId,
    UserId,
)
from medicore.domain.shared.text import fold
from medicore.domain.value_objects.slug import Slug
from tests.support.store import InMemoryStore

_ACTIVE_APPOINTMENTS = {
    AppointmentStatus.SCHEDULED,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.IN_PROGRESS,
}


def _paginate(items: list, paging: Paging | None) -> Page:
    paging = paging or Paging()
    window = items[paging.offset : paging.offset + paging.limit]
    return Page(items=window, total=len(items), offset=paging.offset, limit=paging.limit)


class InMemoryTenantRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        return self._store.tenants.get(tenant_id.value)

    def get_by_slug(self, slug: Slug) -> Tenant | None:
        return next((t for t in self._store.tenants.values() if t.slug == slug), None)

    def list(
        self, filter: TenantFilter | None = None, paging: Paging | None = None
    ) -> Page[Tenant]:
        tenants = list(self._store.tenants.values())
        if filter and filter.status:
            tenants = [t for t in tenants if str(t.status) == filter.status]
        tenants.sort(key=lambda t: t.legal_name)
        return _paginate(tenants, paging)

    def save(self, tenant: Tenant) -> None:
        self._store.tenants[tenant.id.value] = tenant


class InMemoryPlanRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def list(self, include_inactive: bool = True) -> list[Plan]:
        plans = [p for p in self._store.plans.values() if include_inactive or p.active]
        return sorted(plans, key=lambda p: (p.sort_order, p.code))

    def get(self, code: str) -> Plan | None:
        return self._store.plans.get(code)

    def save(self, plan: Plan) -> None:
        self._store.plans[plan.code] = plan


class InMemoryAddonPricingRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get(self) -> AddonPricing:
        return self._store.addon_pricing["current"]

    def save(self, pricing: AddonPricing) -> None:
        self._store.addon_pricing["current"] = pricing


class InMemoryPlatformAdminRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get_by_id(self, admin_id: PlatformAdminId) -> PlatformAdmin | None:
        return self._store.platform_admins.get(admin_id.value)

    def get_by_email(self, email: str) -> PlatformAdmin | None:
        target = email.strip().lower()
        return next(
            (a for a in self._store.platform_admins.values() if a.email.lower() == target),
            None,
        )

    def save(self, admin: PlatformAdmin) -> None:
        self._store.platform_admins[admin.id.value] = admin


class InMemoryPlatformRecoveryCodeRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def replace_all(self, admin_id: PlatformAdminId, code_hashes: list[str], now: datetime) -> None:
        self._store.platform_recovery_codes[admin_id.value] = dict.fromkeys(code_hashes)

    def consume(self, admin_id: PlatformAdminId, code_hash: str, now: datetime) -> bool:
        codes = self._store.platform_recovery_codes.get(admin_id.value, {})
        if code_hash not in codes or codes[code_hash] is not None:
            return False
        codes[code_hash] = now
        return True

    def remaining(self, admin_id: PlatformAdminId) -> int:
        codes = self._store.platform_recovery_codes.get(admin_id.value, {})
        return sum(1 for used_at in codes.values() if used_at is None)

    def delete_all(self, admin_id: PlatformAdminId) -> None:
        self._store.platform_recovery_codes.pop(admin_id.value, None)


class InMemoryPlatformAuditLogRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def append(self, entry: PlatformAuditLog) -> None:
        self._store.platform_audit[entry.id.value] = entry

    def list(self, limit: int = 100, offset: int = 0) -> list[PlatformAuditLog]:
        entries = sorted(
            self._store.platform_audit.values(), key=lambda e: e.timestamp, reverse=True
        )
        return entries[offset : offset + limit]


class InMemoryAuthSessionRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get(self, session_id: SessionId) -> AuthSession | None:
        return self._store.sessions.get(session_id.value)

    def add(self, session: AuthSession) -> None:
        self._store.sessions[session.id.value] = session

    def list_active_for_user(self, user_id, now: datetime) -> list[AuthSession]:
        return sorted(
            (
                s
                for s in self._store.sessions.values()
                if s.user_id == user_id and s.is_active(now)
            ),
            key=lambda s: s.created_at,
            reverse=True,
        )

    def list_active_for_tenant(self, tenant_id: TenantId, now: datetime) -> list[AuthSession]:
        return sorted(
            (
                s
                for s in self._store.sessions.values()
                if s.tenant_id == tenant_id and s.is_active(now)
            ),
            key=lambda s: s.created_at,
            reverse=True,
        )

    def touch(self, session_id: SessionId, now: datetime) -> None:
        session = self._store.sessions.get(session_id.value)
        if session is not None and session.revoked_at is None:
            session.touch(now)

    def revoke(self, session_id: SessionId, now: datetime) -> None:
        session = self._store.sessions.get(session_id.value)
        if session is not None:
            session.revoke(now)

    def consume(self, session_id: SessionId, now: datetime) -> bool:
        session = self._store.sessions.get(session_id.value)
        if session is None or session.revoked_at is not None:
            return False
        session.revoke(now)
        return True

    def revoke_all_for_user(
        self, user_id, now: datetime, except_id: SessionId | None = None
    ) -> None:
        for session in self._store.sessions.values():
            if session.user_id == user_id and (except_id is None or session.id != except_id):
                session.revoke(now)

    def revoke_all_for_tenant(self, tenant_id: TenantId, now: datetime) -> None:
        for session in self._store.sessions.values():
            if session.tenant_id == tenant_id:
                session.revoke(now)

    def delete_expired_for_user(self, user_id, now: datetime) -> None:
        expired = [
            key
            for key, s in self._store.sessions.items()
            if s.user_id == user_id and s.expires_at < now
        ]
        for key in expired:
            del self._store.sessions[key]


class InMemoryLoginThrottleRepository:
    """Same windowing/backoff contract as the SQL repo, sharing the pure policy."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def locked_until(self, identifier: str, now: datetime) -> datetime | None:
        entry = self._store.login_attempts.get(identifier)
        if entry is None:
            return None
        _, _, locked = entry
        if locked is None or locked <= now:
            return None
        return locked

    def record_failure(self, identifier: str, now: datetime) -> datetime | None:
        entry = self._store.login_attempts.get(identifier)
        window_start = now - timedelta(minutes=WINDOW_MINUTES)
        count = 1 if entry is None or entry[1] < window_start else entry[0] + 1
        locked = lockout_until(count, now)
        self._store.login_attempts[identifier] = (count, now, locked)
        return locked

    def reset(self, identifier: str) -> None:
        self._store.login_attempts.pop(identifier, None)

    def purge_stale(self, now: datetime) -> None:
        window_start = now - timedelta(minutes=WINDOW_MINUTES)
        for identifier, (_, last, locked) in list(self._store.login_attempts.items()):
            if last < window_start and (locked is None or locked <= now):
                del self._store.login_attempts[identifier]


class InMemoryDiagnosisCatalogRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def _norm(self, text: str) -> str:
        import unicodedata

        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()

    def search(self, version: str, query: str, limit: int = 20):
        q = (query or "").strip()
        if not q:
            return []
        norm = self._norm(q)
        prefix = q.upper()
        matches = [
            e
            for e in self._store.diagnosis_codes.values()
            if e.version == version
            and (e.code.upper().startswith(prefix) or norm in self._norm(f"{e.code} {e.label}"))
        ]
        # Same ranking contract as the SQL repo: code-prefix matches first, shorter
        # (more general) codes winning ties.
        matches.sort(key=lambda e: (not e.code.upper().startswith(prefix), len(e.code), e.code))
        return matches[:limit]

    def count(self, version: str) -> int:
        return sum(1 for e in self._store.diagnosis_codes.values() if e.version == version)

    def upsert(self, entry) -> None:
        self._store.diagnosis_codes[f"{entry.version}:{entry.code}"] = entry


class InMemoryPlatformReadModel:
    _SOURCES = ("patients", "users", "appointments", "consultations", "medical_records")
    _KEYS = {"medical_records": "records"}

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def _items(self, name: str):
        return getattr(self._store, name).values()

    def tenant_counts(self, tenant_id: TenantId) -> dict[str, int]:
        out: dict[str, int] = {}
        for name in self._SOURCES:
            key = self._KEYS.get(name, name)
            out[key] = sum(1 for e in self._items(name) if e.tenant_id == tenant_id)
        return out

    def active_staff_by_tenant(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for u in self._store.users.values():
            if u.is_active:
                by_role = out.setdefault(str(u.tenant_id), {})
                by_role[str(u.role)] = by_role.get(str(u.role), 0) + 1
        return out

    def payments_since(self, day):
        from medicore.domain.repositories._support import PaymentSummary

        return [
            PaymentSummary(str(p.tenant_id), p.amount.amount, p.paid_on)
            for p in self._store.subscription_payments.values()
            if p.paid_on >= day
        ]

    def activity_by_tenant(self, active_since, signed_since):
        from medicore.domain.repositories._support import TenantActivity

        out = {}
        tenants = {str(e.tenant_id) for e in self._store.audit.values()} | {
            str(r.tenant_id) for r in self._store.medical_records.values()
        }
        for tid in tenants:
            entries = [e for e in self._store.audit.values() if str(e.tenant_id) == tid]
            out[tid] = TenantActivity(
                last_activity=max((e.timestamp for e in entries), default=None),
                active_users=len({e.actor_id for e in entries if e.timestamp >= active_since}),
                signed_records=sum(
                    1 for r in self._store.medical_records.values()
                    if str(r.tenant_id) == tid and r.signed_at >= signed_since
                ),
            )
        return out

    def signed_per_week(self, since):
        from collections import Counter
        from datetime import timedelta

        weeks = Counter(
            (r.signed_at.date() - timedelta(days=r.signed_at.weekday()))
            for r in self._store.medical_records.values()
            if r.signed_at >= since
        )
        return sorted(weeks.items())

    def global_audit(
        self,
        limit: int = 100,
        offset: int = 0,
        category: str | None = None,
    ) -> Page:
        users = {str(u.id): u.name for u in self._store.users.values()}
        admins = {str(a.id): a.name for a in self._store.platform_admins.values()}
        clinics = {str(t.id): t.legal_name for t in self._store.tenants.values()}

        rows: list[tuple] = [(e, "tenant") for e in self._store.audit.values()]
        rows += [(e, "platform") for e in self._store.platform_audit.values()]
        rows.sort(key=lambda pair: pair[0].timestamp, reverse=True)
        if category:
            rows = [r for r in rows if r[0].action.startswith(f"{category}.")]
        total = len(rows)

        items = []
        for e, kind in rows[offset : offset + limit]:
            tid = str(e.tenant_id) if getattr(e, "tenant_id", None) else None
            items.append(
                GlobalAuditRow(
                    id=str(e.id),
                    timestamp=e.timestamp,
                    source_kind=kind,
                    actor_name=(
                        users.get(str(e.actor_id))
                        if kind == "tenant"
                        else admins.get(str(e.actor_id))
                    ),
                    action=e.action,
                    clinic_name=clinics.get(tid) if tid else None,
                    metadata=dict(e.metadata),
                    ip_address=getattr(e, "ip_address", None),
                )
            )
        return Page(items=items, total=total, offset=offset, limit=limit)


class _Scoped:
    def __init__(self, store: InMemoryStore, tenant_id: TenantId) -> None:
        self._store = store
        self._tenant = tenant_id

    def _mine(self, items) -> list:
        return [e for e in items if e.tenant_id == self._tenant]


class InMemoryUserRepository(_Scoped):
    def get_by_id(self, user_id: UserId) -> User | None:
        user = self._store.users.get(user_id.value)
        return user if user and user.tenant_id == self._tenant else None

    def get_by_email(self, email: str) -> User | None:
        target = email.strip().lower()
        return next(
            (u for u in self._mine(self._store.users.values()) if u.email.lower() == target),
            None,
        )

    def list(self, filter: UserFilter | None = None, paging: Paging | None = None) -> Page[User]:
        users = self._mine(self._store.users.values())
        if filter and filter.role:
            users = [u for u in users if str(u.role) == filter.role]
        if filter and filter.status:
            users = [u for u in users if str(u.status) == filter.status]
        users.sort(key=lambda u: u.name)
        return _paginate(users, paging)

    def save(self, user: User) -> None:
        self._store.users[user.id.value] = user


class InMemoryDoctorProfileRepository(_Scoped):
    def get_by_user_id(self, user_id: UserId) -> DoctorProfile | None:
        return next(
            (
                p
                for p in self._mine(self._store.doctor_profiles.values())
                if p.user_id == user_id
            ),
            None,
        )

    def save(self, profile: DoctorProfile) -> None:
        self._store.doctor_profiles[profile.id.value] = profile


class InMemoryPatientRepository(_Scoped):
    def count_created_since(self, since: datetime) -> int:
        return sum(1 for p in self._mine(self._store.patients.values()) if p.created_at >= since)

    def get_by_id(self, patient_id: PatientId) -> Patient | None:
        p = self._store.patients.get(patient_id.value)
        return p if p and p.tenant_id == self._tenant else None

    def list(
        self, filter: PatientFilter | None = None, paging: Paging | None = None
    ) -> Page[Patient]:
        patients = self._mine(self._store.patients.values())
        if filter and filter.status:
            patients = [p for p in patients if str(p.status) == filter.status]
        if filter and filter.doctor_id:
            patients = [
                p
                for p in patients
                if p.primary_doctor_id and str(p.primary_doctor_id) == filter.doctor_id
            ]
        if filter and filter.tags:
            patients = [p for p in patients if set(filter.tags).issubset(p.tags)]
        patients.sort(key=lambda p: (p.last_name, p.first_name))
        return _paginate(patients, paging)

    def search(
        self, query: str, paging: Paging | None = None, filter: PatientFilter | None = None
    ) -> Page[Patient]:
        candidates = self.list(filter, Paging(limit=10_000)).items
        words = fold(query).split()

        def hit(p: Patient, word: str) -> bool:
            digits = "".join(ch for ch in word if ch.isdigit())
            phone = "".join(ch for ch in (p.contact.phone or "") if ch.isdigit())
            return (
                word in fold(p.full_name)
                or word in p.code.lower()
                or (len(digits) >= 3 and digits in phone)
            )

        matches = [p for p in candidates if all(hit(p, w) for w in words)]
        return _paginate(matches, paging)

    def save(self, patient: Patient) -> None:
        self._store.patients[patient.id.value] = patient


class InMemoryAppointmentRepository(_Scoped):
    def get_by_id(self, appointment_id: AppointmentId) -> Appointment | None:
        a = self._store.appointments.get(appointment_id.value)
        return a if a and a.tenant_id == self._tenant else None

    def list_by_day(self, on: date, doctor_id: UserId | None = None) -> list[Appointment]:
        result = [
            a
            for a in self._mine(self._store.appointments.values())
            if a.scheduled_start.date() == on
            and (doctor_id is None or a.doctor_id == doctor_id)
        ]
        result.sort(key=lambda a: a.scheduled_start)
        return result

    def list_by_patient(self, patient_id: PatientId) -> list[Appointment]:
        result = [
            a for a in self._mine(self._store.appointments.values()) if a.patient_id == patient_id
        ]
        result.sort(key=lambda a: a.scheduled_start)
        return result

    def next_visits(
        self, patient_ids: list[PatientId], now: datetime
    ) -> dict[PatientId, datetime]:
        wanted = set(patient_ids)
        result: dict[PatientId, datetime] = {}
        for a in self._mine(self._store.appointments.values()):
            if a.patient_id not in wanted or not a.is_active or a.scheduled_start <= now:
                continue
            current = result.get(a.patient_id)
            if current is None or a.scheduled_start < current:
                result[a.patient_id] = a.scheduled_start
        return result

    def last_visits(self, patient_ids: list[PatientId]) -> dict[PatientId, datetime]:
        wanted = set(patient_ids)
        result: dict[PatientId, datetime] = {}
        for a in self._mine(self._store.appointments.values()):
            if a.patient_id not in wanted or a.status != AppointmentStatus.COMPLETED:
                continue
            current = result.get(a.patient_id)
            if current is None or a.scheduled_start > current:
                result[a.patient_id] = a.scheduled_start
        return result

    def exists_for_doctor(self, doctor_id: UserId) -> bool:
        return any(
            a.doctor_id == doctor_id for a in self._mine(self._store.appointments.values())
        )

    def count_patients_with_upcoming(self, now: datetime) -> int:
        return len(
            {
                a.patient_id
                for a in self._mine(self._store.appointments.values())
                if a.is_active and a.scheduled_start > now
            }
        )

    def list_upcoming(
        self, after: datetime, limit: int, doctor_id: UserId | None = None
    ) -> list[Appointment]:
        pending = {AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED}
        result = [
            a
            for a in self._mine(self._store.appointments.values())
            if a.status in pending
            and a.scheduled_start >= after
            and (doctor_id is None or a.doctor_id == doctor_id)
        ]
        result.sort(key=lambda a: (a.scheduled_start, a.code))
        return result[:limit]

    def find_overlapping(
        self, doctor_id: UserId, start: datetime, end: datetime
    ) -> list[Appointment]:
        return [
            a
            for a in self._mine(self._store.appointments.values())
            if a.doctor_id == doctor_id
            and a.status in _ACTIVE_APPOINTMENTS
            and a.scheduled_start < end
            and start < a.scheduled_end
        ]

    def save(self, appointment: Appointment) -> None:
        self._store.appointments[appointment.id.value] = appointment


class InMemoryVaccinationRecordRepository(_Scoped):
    def get_by_id(self, record_id):
        r = self._store.vaccinations.get(record_id.value)
        return r if r and r.tenant_id == self._tenant else None

    def list_by_patient(self, patient_id) -> list:
        result = [r for r in self._mine(self._store.vaccinations.values())
                  if r.patient_id == patient_id]
        result.sort(key=lambda r: (r.occurred_on, r.created_at), reverse=True)
        return result

    def list_active_by_patients(self, patient_ids) -> list:
        wanted = set(patient_ids)
        return [r for r in self._mine(self._store.vaccinations.values())
                if r.patient_id in wanted and not r.is_voided]

    def list_administered_on(self, day) -> list:
        from medicore.domain.enums import VaccinationOutcome, VaccinationSource

        return [
            r for r in self._mine(self._store.vaccinations.values())
            if r.occurred_on == day and not r.is_voided
            and r.outcome == VaccinationOutcome.ADMINISTERED
            and r.source == VaccinationSource.CLINIC
        ]

    def save(self, record) -> None:
        self._store.vaccinations[record.id.value] = record


class InMemoryApplicationRepository(_Scoped):
    def get_order(self, order_id):
        o = self._store.application_orders.get(order_id.value)
        return o if o and o.tenant_id == self._tenant else None

    def list_orders_by_patient(self, patient_id) -> list:
        result = [o for o in self._mine(self._store.application_orders.values())
                  if o.patient_id == patient_id]
        result.sort(key=lambda o: o.created_at, reverse=True)
        return result

    def list_open_orders(self) -> list:
        result = [o for o in self._mine(self._store.application_orders.values()) if o.is_open]
        result.sort(key=lambda o: o.starts_at)
        return result

    def save_order(self, order) -> None:
        self._store.application_orders[order.id.value] = order

    def get_record(self, record_id):
        r = self._store.application_records.get(record_id.value)
        return r if r and r.tenant_id == self._tenant else None

    def list_records_by_orders(self, order_ids) -> list:
        wanted = set(order_ids)
        result = [r for r in self._mine(self._store.application_records.values())
                  if r.order_id in wanted]
        result.sort(key=lambda r: r.recorded_at)
        return result

    def list_records_between(self, start, end) -> list:
        result = [r for r in self._mine(self._store.application_records.values())
                  if start <= r.recorded_at < end and not r.is_voided]
        result.sort(key=lambda r: r.recorded_at, reverse=True)
        return result

    def list_observing(self) -> list:
        result = [r for r in self._mine(self._store.application_records.values())
                  if r.observing]
        result.sort(key=lambda r: r.observe_until)
        return result

    def save_record(self, record) -> None:
        self._store.application_records[record.id.value] = record


class InMemoryProcedureRepository(_Scoped):
    def get_type(self, type_id):
        t = self._store.procedure_types.get(type_id.value)
        return t if t and t.tenant_id == self._tenant else None

    def list_types(self) -> list:
        return sorted(self._mine(self._store.procedure_types.values()), key=lambda t: t.name)

    def save_type(self, kind) -> None:
        self._store.procedure_types[kind.id.value] = kind

    def get(self, procedure_id):
        p = self._store.procedures.get(procedure_id.value)
        return p if p and p.tenant_id == self._tenant else None

    def list_by_patient(self, patient_id) -> list:
        result = [p for p in self._mine(self._store.procedures.values())
                  if p.patient_id == patient_id]
        result.sort(key=lambda p: p.created_at, reverse=True)
        return result

    def list_open(self) -> list:
        result = [p for p in self._mine(self._store.procedures.values()) if p.is_open]
        result.sort(key=lambda p: p.created_at)
        return result

    def list_by_appointments(self, appointment_ids) -> list:
        wanted = set(appointment_ids)
        return [p for p in self._mine(self._store.procedures.values())
                if p.appointment_id in wanted]

    def list_completed_between(self, start, end) -> list:
        result = [p for p in self._mine(self._store.procedures.values())
                  if p.status == ProcedureStatus.COMPLETED and start <= p.performed_at < end]
        result.sort(key=lambda p: p.performed_at, reverse=True)
        return result

    def save(self, procedure) -> None:
        self._store.procedures[procedure.id.value] = procedure


class InMemoryInsurerRepository(_Scoped):
    def get_by_id(self, insurer_id) -> object | None:
        ins = self._store.insurers.get(insurer_id.value)
        return ins if ins and ins.tenant_id == self._tenant else None

    def list(self, active_only: bool = False) -> list:
        result = [
            i
            for i in self._mine(self._store.insurers.values())
            if not active_only or i.active
        ]
        result.sort(key=lambda i: i.name)
        return result

    def save(self, insurer) -> None:
        self._store.insurers[insurer.id.value] = insurer


class InMemoryNoteTemplateRepository(_Scoped):
    def get_by_id(self, template_id) -> object | None:
        t = self._store.note_templates.get(template_id.value)
        return t if t and t.tenant_id == self._tenant else None

    def list(self, include_archived: bool = False) -> list:
        result = [t for t in self._mine(self._store.note_templates.values())
                  if include_archived or not t.archived]
        result.sort(key=lambda t: t.created_at)
        return result

    def save(self, template) -> None:
        self._store.note_templates[template.id.value] = template


class InMemoryRolePermissionOverrideRepository(_Scoped):
    def get_by_role(self, role) -> object | None:
        return next(
            (
                o
                for o in self._mine(self._store.role_permission_overrides.values())
                if o.role == role
            ),
            None,
        )

    def list(self) -> list:
        result = self._mine(self._store.role_permission_overrides.values())
        result.sort(key=lambda o: str(o.role))
        return result

    def save(self, override) -> None:
        self._store.role_permission_overrides[override.id.value] = override

    def delete_by_role(self, role) -> None:
        for key, o in list(self._store.role_permission_overrides.items()):
            if o.tenant_id == self._tenant and o.role == role:
                del self._store.role_permission_overrides[key]


class InMemoryConsultationRepository(_Scoped):
    def get_by_id(self, consultation_id: ConsultationId) -> Consultation | None:
        c = self._store.consultations.get(consultation_id.value)
        return c if c and c.tenant_id == self._tenant else None

    def get_by_appointment(self, appointment_id: AppointmentId) -> Consultation | None:
        return next(
            (
                c
                for c in self._mine(self._store.consultations.values())
                if c.appointment_id == appointment_id
            ),
            None,
        )

    def save(self, consultation: Consultation) -> None:
        self._store.consultations[consultation.id.value] = consultation


class InMemoryMedicalRecordRepository(_Scoped):
    def get_by_id(self, record_id: RecordId) -> MedicalRecord | None:
        r = self._store.medical_records.get(record_id.value)
        return r if r and r.tenant_id == self._tenant else None

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalRecord]:
        result = [
            r
            for r in self._mine(self._store.medical_records.values())
            if r.patient_id == patient_id
        ]
        result.sort(key=lambda r: r.encounter_at, reverse=True)
        return result

    def list(self, filter: RecordFilter | None = None) -> list[MedicalRecord]:
        records = self._mine(self._store.medical_records.values())
        if filter and filter.patient_id:
            records = [r for r in records if str(r.patient_id) == filter.patient_id]
        if filter and filter.type:
            records = [r for r in records if str(r.type) == filter.type]
        records.sort(key=lambda r: r.encounter_at, reverse=True)
        return records

    def exists_by_author(self, author_id: UserId) -> bool:
        return any(
            r.author_id == author_id for r in self._mine(self._store.medical_records.values())
        )

    def save(self, record: MedicalRecord) -> None:
        self._store.medical_records[record.id.value] = record


class InMemoryPrescriptionRepository(_Scoped):
    def get_by_id(self, prescription_id: PrescriptionId) -> Prescription | None:
        p = self._store.prescriptions.get(prescription_id.value)
        return p if p and p.tenant_id == self._tenant else None

    def list_by_patient(
        self, patient_id: PatientId, active_only: bool = False
    ) -> list[Prescription]:
        from medicore.domain.enums import PrescriptionStatus

        result = [
            p
            for p in self._mine(self._store.prescriptions.values())
            if p.patient_id == patient_id
            and (not active_only or p.status == PrescriptionStatus.ACTIVE)
        ]
        result.sort(key=lambda p: p.start_date, reverse=True)
        return result

    def save(self, prescription: Prescription) -> None:
        self._store.prescriptions[prescription.id.value] = prescription


class InMemoryMedicalDocumentRepository(_Scoped):
    def list_by_patient(self, patient_id: PatientId) -> list[MedicalDocument]:
        result = [
            d for d in self._mine(self._store.documents.values()) if d.patient_id == patient_id
        ]
        result.sort(key=lambda d: d.uploaded_at, reverse=True)
        return result

    def save(self, document: MedicalDocument) -> None:
        self._store.documents[document.id.value] = document

    def delete(self, document_id: DocumentId) -> None:
        self._store.documents.pop(document_id.value, None)


class InMemoryDoctorAvailabilityRepository(_Scoped):
    def get_by_doctor(self, doctor_id: UserId) -> DoctorAvailability | None:
        return next(
            (
                a
                for a in self._mine(self._store.availability.values())
                if a.doctor_id == doctor_id
            ),
            None,
        )

    def list_for_doctors(self, doctor_ids: list[UserId]) -> dict[UserId, DoctorAvailability]:
        wanted = set(doctor_ids)
        return {
            a.doctor_id: a
            for a in self._mine(self._store.availability.values())
            if a.doctor_id in wanted
        }

    def save(self, availability: DoctorAvailability) -> None:
        self._store.availability[availability.id.value] = availability


class InMemoryFeeScheduleRepository(_Scoped):
    def get_by_doctor(self, doctor_id: UserId) -> FeeSchedule | None:
        return next(
            (f for f in self._mine(self._store.fees.values()) if f.doctor_id == doctor_id), None
        )

    def list_for_doctors(self, doctor_ids: list[UserId]) -> dict[UserId, FeeSchedule]:
        wanted = set(doctor_ids)
        return {f.doctor_id: f for f in self._mine(self._store.fees.values())
                if f.doctor_id in wanted}

    def save(self, schedule: FeeSchedule) -> None:
        self._store.fees[schedule.id.value] = schedule


class InMemoryNotificationRepository(_Scoped):
    def _of(self, user_id: UserId) -> list[Notification]:
        return [n for n in self._mine(self._store.notifications.values()) if n.user_id == user_id]

    def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        n = self._store.notifications.get(notification_id.value)
        return n if n and n.tenant_id == self._tenant else None

    def list_by_user(
        self,
        user_id: UserId,
        unread_only: bool = False,
        paging: Paging | None = None,
        category: str | None = None,
    ) -> list[Notification]:
        paging = paging or Paging()
        result = [
            n
            for n in self._of(user_id)
            if (not unread_only or not n.is_read)
            and (not category or n.type.startswith(f"{category}."))
        ]
        result.sort(key=lambda n: (n.created_at, n.id.value), reverse=True)
        return result[paging.offset : paging.offset + paging.limit]

    def count_unread(self, user_id: UserId) -> int:
        return sum(1 for n in self._of(user_id) if not n.is_read)

    def mark_all_read(self, user_id: UserId, when: datetime) -> int:
        unread = [n for n in self._of(user_id) if not n.is_read]
        for n in unread:
            n.mark_read(when)
        return len(unread)

    def delete_read_before(self, user_id: UserId, cutoff: datetime) -> int:
        stale = [n for n in self._of(user_id) if n.read_at is not None and n.read_at < cutoff]
        for n in stale:
            del self._store.notifications[n.id.value]
        return len(stale)

    def save(self, notification: Notification) -> None:
        self._store.notifications[notification.id.value] = notification


class InMemoryAuditLogRepository(_Scoped):
    def append(self, entry: AuditLog) -> None:
        self._store.audit[entry.id.value] = entry

    def query(self, **criteria: object) -> list[AuditLog]:
        entries = self._mine(self._store.audit.values())
        for key, value in criteria.items():
            entries = [e for e in entries if getattr(e, key, None) == value]
        entries.sort(key=lambda e: e.timestamp)
        return entries

    def list(
        self, filter: AuditFilter | None = None, paging: Paging | None = None
    ) -> Page[AuditLog]:
        paging = paging or Paging()
        entries = list(self._mine(self._store.audit.values()))
        if filter:
            if filter.action:
                entries = [e for e in entries if e.action == filter.action]
            if filter.category:
                entries = [e for e in entries if e.action.startswith(f"{filter.category}.")]
            if filter.entity_type:
                entries = [e for e in entries if e.entity_type == filter.entity_type]
            if filter.actor_id:
                entries = [e for e in entries if str(e.actor_id) == filter.actor_id]
            if filter.date_from:
                entries = [e for e in entries if e.timestamp.date().isoformat() >= filter.date_from]
            if filter.date_to:
                entries = [e for e in entries if e.timestamp.date().isoformat() <= filter.date_to]
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        total = len(entries)
        window = entries[paging.offset : paging.offset + paging.limit]
        return Page(items=window, total=total, offset=paging.offset, limit=paging.limit)


class InMemorySubscriptionPaymentRepository(_Scoped):
    def list(self) -> list:
        return sorted(
            self._mine(self._store.subscription_payments.values()),
            key=lambda p: (p.paid_on, p.recorded_at),
            reverse=True,
        )

    def save(self, payment) -> None:
        self._store.subscription_payments[payment.id.value] = payment


class InMemoryMonitoringReadModel:
    """Same contract as the SQL read model; the database facts are fixed test values."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def ping(self) -> None:
        if self._store.database_down:
            raise ConnectionError("database unreachable")

    def database(self) -> DatabaseStatus:
        return DatabaseStatus(version="16.0 (in-memory)", size_bytes=0, revision="head")

    def largest_tables(self, limit: int) -> list[TableSize]:
        return []

    def login_pressure(self, since: datetime, now: datetime) -> LoginPressure:
        recent = [
            (ident, count, locked)
            for ident, (count, last, locked) in self._store.login_attempts.items()
            if last >= since
        ]
        locked = []
        for ident, (count, _, until) in self._store.login_attempts.items():
            if until is not None and until > now:
                scope, _, rest = ident.partition(":")
                slug, email = rest.split(":", 1) if scope == "tenant" else (None, rest)
                locked.append(LockedLogin(scope, slug, email, count, until))
        locked.sort(key=lambda lk: lk.locked_until, reverse=True)
        return LoginPressure(
            failing_accounts=len(recent),
            failed_attempts=sum(count for _, count, _ in recent),
            locked=locked,
        )

    def lockouts_since(self, since: datetime) -> int:
        clinic = sum(
            1 for a in self._store.audit.values()
            if a.action == "auth.login_locked" and a.timestamp >= since
        )
        console = sum(
            1 for a in self._store.platform_audit.values()
            if a.action == "auth.platform_login_locked" and a.timestamp >= since
        )
        return clinic + console

    def console_logins(self, limit: int) -> list[ConsoleLogin]:
        rows = sorted(
            (a for a in self._store.platform_audit.values()
             if a.action.startswith("auth.platform_login")),
            key=lambda a: a.timestamp, reverse=True,
        )[:limit]
        out = []
        for a in rows:
            admin = self._store.platform_admins.get(a.actor_id.value)
            out.append(ConsoleLogin(
                admin.name if admin else None, a.action, a.timestamp, a.ip_address, a.user_agent
            ))
        return out

    def connections(self) -> ConnectionStats:
        return ConnectionStats(
            total=1, active=1, idle=0, idle_in_transaction=0, max_connections=100
        )

    def errors_per_day(self, since: datetime) -> list[tuple[date, int]]:
        days: dict[date, int] = {}
        for e in self._store.error_events.values():
            if e.occurred_at >= since:
                days[e.occurred_at.date()] = days.get(e.occurred_at.date(), 0) + 1
        return sorted(days.items())

    def job_summaries(self) -> list[JobSummary]:
        by_job: dict[str, list[JobRun]] = {}
        for run in self._store.job_runs.values():
            by_job.setdefault(run.job, []).append(run)
        out = []
        for job, runs in sorted(by_job.items()):
            last = max(runs, key=lambda r: r.finished_at)
            ok = [r.finished_at for r in runs if r.ok]
            out.append(JobSummary(
                job, last.started_at, last.finished_at, last.ok, last.detail,
                max(ok) if ok else None,
            ))
        return out

    def sessions_by_kind(self, now: datetime) -> dict[str, int]:
        out = {"tenant": 0, "support": 0, "platform": 0}
        for s in self._store.sessions.values():
            if s.is_active(now) and s.scope != "mfa":
                out["support" if s.impersonator_id else s.scope] += 1
        return out

    def active_impersonations(self, now: datetime) -> list[ActiveImpersonation]:
        rows = []
        for s in self._store.sessions.values():
            if not s.impersonator_id or not s.is_active(now):
                continue
            admin = self._store.platform_admins.get(s.impersonator_id)
            tenant = self._store.tenants.get(s.tenant_id.value) if s.tenant_id else None
            rows.append(ActiveImpersonation(
                session_id=str(s.id),
                admin_name=admin.name if admin else None,
                tenant_id=str(s.tenant_id) if s.tenant_id else None,
                clinic_name=tenant.legal_name if tenant else None,
                started_at=s.created_at,
                expires_at=s.expires_at,
                ip_address=s.ip_address,
            ))
        return sorted(rows, key=lambda r: r.started_at, reverse=True)

    def errors_since(self, since: datetime) -> int:
        return sum(1 for e in self._store.error_events.values() if e.occurred_at >= since)

    def error_groups(self, since: datetime, limit: int) -> list[ErrorGroup]:
        groups: dict[tuple, list[ErrorEvent]] = {}
        for e in self._store.error_events.values():
            if e.occurred_at >= since:
                groups.setdefault((e.method, e.route, e.error_type, e.location), []).append(e)
        out = []
        for key, evs in groups.items():
            evs.sort(key=lambda e: e.occurred_at)
            out.append(ErrorGroup(
                *key, count=len(evs), last_at=evs[-1].occurred_at, first_at=evs[0].occurred_at,
                first_commit=evs[0].commit, last_commit=evs[-1].commit,
            ))
        out.sort(key=lambda g: (g.count, g.last_at), reverse=True)
        return out[:limit]

    def request_stats_since(self, since: datetime) -> list[RequestStatsRow]:
        return [r for r in self._store.request_stats.values() if r.hour >= since]

    def recent_errors(self, limit: int, offset: int) -> Page[ErrorEvent]:
        items = sorted(
            self._store.error_events.values(), key=lambda e: e.occurred_at, reverse=True
        )
        return Page(items=items[offset:offset + limit], total=len(items), offset=offset,
                    limit=limit)


class InMemoryErrorLogRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def record(self, event: ErrorEvent) -> None:
        self._store.error_events[event.id] = event

    def purge_before(self, cutoff: datetime) -> None:
        for key, e in list(self._store.error_events.items()):
            if e.occurred_at < cutoff:
                del self._store.error_events[key]


class InMemoryJobLogRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def record(self, run: JobRun) -> None:
        self._store.job_runs[run.id] = run

    def purge_before(self, cutoff: datetime) -> None:
        for key, run in list(self._store.job_runs.items()):
            if run.finished_at < cutoff:
                del self._store.job_runs[key]


class InMemoryRequestStatsRepository:
    """Same summing contract as the SQL upsert."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def add(self, rows: list[RequestStatsRow]) -> None:
        for r in rows:
            key = (r.hour, r.method, r.route)
            old = self._store.request_stats.get(key)
            if old is not None:
                r = RequestStatsRow(
                    hour=r.hour, method=r.method, route=r.route, count=old.count + r.count,
                    client_errors=old.client_errors + r.client_errors,
                    server_errors=old.server_errors + r.server_errors,
                    total_ms=old.total_ms + r.total_ms, max_ms=max(old.max_ms, r.max_ms),
                    buckets=tuple(a + b for a, b in zip(old.buckets, r.buckets, strict=True)),
                )
            self._store.request_stats[key] = r

    def purge_before(self, cutoff: datetime) -> None:
        for key in [k for k in self._store.request_stats if k[0] < cutoff]:
            del self._store.request_stats[key]



def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


class InMemoryAnalyticsReadModel(_Scoped):
    """Instants are compared without tzinfo: the tests' clocks are naive."""

    def appointment_facts(
        self, start: datetime, end: datetime, doctor_id: UserId | None = None
    ) -> list[AppointmentFact]:
        return [
            AppointmentFact(
                doctor_id=str(a.doctor_id), patient_id=str(a.patient_id), type=str(a.type),
                status=str(a.status), scheduled_start=a.scheduled_start,
                created_at=a.created_at,
                insurer_id=str(a.insurance_id) if a.insurance_id else None,
                charged=a.charge.charged.amount if a.charge.charged else None,
            )
            for a in self._mine(self._store.appointments.values())
            if start <= a.scheduled_start < end
            and (doctor_id is None or a.doctor_id == doctor_id)
        ]

    def first_visits(
        self, patient_ids: list[PatientId], doctor_id: UserId | None = None
    ) -> dict[PatientId, datetime]:
        wanted = set(patient_ids)
        first: dict[PatientId, datetime] = {}
        for a in self._mine(self._store.appointments.values()):
            if (
                a.patient_id in wanted
                and a.status == AppointmentStatus.COMPLETED
                and (doctor_id is None or a.doctor_id == doctor_id)
                and (a.patient_id not in first or a.scheduled_start < first[a.patient_id])
            ):
                first[a.patient_id] = a.scheduled_start
        return first

    def procedure_facts(
        self, since: datetime, until: datetime, doctor_id: UserId | None = None
    ) -> list[ProcedureFact]:
        return [
            ProcedureFact(
                doctor_id=str(p.ordered_by_id), performed_at=p.performed_at,
                charged=None if p.fee_included or p.charge.charged is None
                else p.charge.charged.amount,
            )
            for p in self._mine(self._store.procedures.values())
            if p.status == ProcedureStatus.COMPLETED and p.performed_at is not None
            and _naive(since) <= _naive(p.performed_at) < _naive(until)
            and (doctor_id is None or p.ordered_by_id == doctor_id)
        ]

    def vaccinations_recorded(
        self, first: date, last: date, user_id: UserId | None = None
    ) -> int:
        return sum(
            1 for v in self._mine(self._store.vaccinations.values())
            if v.voided_at is None and first <= v.occurred_on <= last
            and (user_id is None or v.recorded_by_id == user_id)
        )

    def applications_recorded(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> int:
        return sum(
            1 for r in self._mine(self._store.application_records.values())
            if r.voided_at is None and r.outcome == ApplicationOutcome.APPLIED
            and _naive(since) <= _naive(r.recorded_at) < _naive(until)
            and (user_id is None or r.recorded_by_id == user_id)
        )


class InMemoryReportReadModel(_Scoped):
    """Same rows as the SQL adapter; instants compared without tzinfo (naive test clocks)."""

    def _patient(self, patient_id: PatientId) -> Patient:
        return self._store.patients[patient_id.value]

    def appointment_rows(
        self, start: datetime, end: datetime, user_id: UserId | None = None
    ) -> list[AppointmentReportRow]:
        rows = []
        for a in sorted(self._mine(self._store.appointments.values()),
                        key=lambda a: (a.scheduled_start, a.code)):
            if not (start <= a.scheduled_start < end) or (
                user_id is not None and a.doctor_id != user_id
            ):
                continue
            p = self._patient(a.patient_id)
            rows.append(AppointmentReportRow(
                code=a.code, scheduled_start=a.scheduled_start, patient_code=p.code,
                patient_name=p.full_name, patient_phone=p.contact.phone,
                doctor_id=str(a.doctor_id), type=str(a.type), status=str(a.status),
                insurer_id=str(a.insurance_id) if a.insurance_id else None,
                listed=a.charge.listed.amount if a.charge.listed else None,
                charged=a.charge.charged.amount if a.charge.charged else None,
                fee_note=a.charge.note,
            ))
        return rows

    def procedure_rows(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> list[ProcedureReportRow]:
        done = [
            p for p in self._mine(self._store.procedures.values())
            if p.status == ProcedureStatus.COMPLETED and p.performed_at is not None
            and _naive(since) <= _naive(p.performed_at) < _naive(until)
            and (user_id is None or p.ordered_by_id == user_id)
        ]
        rows = []
        for pr in sorted(done, key=lambda p: _naive(p.performed_at)):
            patient = self._patient(pr.patient_id)
            rows.append(ProcedureReportRow(
                type_name=pr.type_name, performed_at=pr.performed_at,
                patient_code=patient.code, patient_name=patient.full_name,
                ordered_by_id=str(pr.ordered_by_id),
                performed_by_id=str(pr.performed_by_id) if pr.performed_by_id else None,
                listed=pr.charge.listed.amount if pr.charge.listed else None,
                charged=None if pr.fee_included or pr.charge.charged is None
                else pr.charge.charged.amount,
                included=pr.fee_included,
            ))
        return rows

    def vaccination_rows(
        self, first: date, last: date, user_id: UserId | None = None
    ) -> list[VaccinationReportRow]:
        given = [
            v for v in self._mine(self._store.vaccinations.values())
            if v.voided_at is None and v.outcome == VaccinationOutcome.ADMINISTERED
            and v.source == VaccinationSource.CLINIC and first <= v.occurred_on <= last
            and (user_id is None or v.recorded_by_id == user_id)
        ]
        rows = []
        for v in sorted(given, key=lambda v: (v.occurred_on, _naive(v.created_at))):
            p = self._patient(v.patient_id)
            rows.append(VaccinationReportRow(
                occurred_on=v.occurred_on, patient_code=p.code, patient_name=p.full_name,
                patient_sex=str(p.sex), date_of_birth=p.date_of_birth,
                vaccine_code=v.vaccine_code, dose_key=v.dose_key, lot=v.lot,
                recorded_by_id=str(v.recorded_by_id),
            ))
        return rows

    def application_rows(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> list[ApplicationReportRow]:
        applied = [
            r for r in self._mine(self._store.application_records.values())
            if r.voided_at is None and r.outcome == ApplicationOutcome.APPLIED
            and _naive(since) <= _naive(r.recorded_at) < _naive(until)
            and (user_id is None or r.recorded_by_id == user_id)
        ]
        rows = []
        for r in sorted(applied, key=lambda r: _naive(r.recorded_at)):
            order = self._store.application_orders[r.order_id.value]
            p = self._patient(r.patient_id)
            rows.append(ApplicationReportRow(
                recorded_at=r.recorded_at, patient_code=p.code, patient_name=p.full_name,
                drug=order.drug, dose=order.dose, route=str(order.route),
                dose_number=r.dose_number, lot=r.lot, recorded_by_id=str(r.recorded_by_id),
            ))
        return rows


class InMemoryMedicalCertificateRepository(_Scoped):
    def get_by_id(self, certificate_id: CertificateId) -> MedicalCertificate | None:
        c = self._store.certificates.get(certificate_id.value)
        return c if c and c.tenant_id == self._tenant else None

    def list_by_patient(self, patient_id: PatientId) -> list[MedicalCertificate]:
        mine = [c for c in self._mine(self._store.certificates.values())
                if c.patient_id == patient_id]
        return sorted(mine, key=lambda c: c.issued_at, reverse=True)

    def list_by_record(self, record_id: RecordId) -> list[MedicalCertificate]:
        mine = [c for c in self._mine(self._store.certificates.values())
                if c.record_id == record_id]
        return sorted(mine, key=lambda c: c.issued_at, reverse=True)

    def save(self, certificate: MedicalCertificate) -> None:
        self._store.certificates[certificate.id.value] = certificate
