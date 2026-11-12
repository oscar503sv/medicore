"""UnitOfWork port — a transactional boundary that exposes the tenant-scoped repositories.

A UnitOfWork is bound to a single tenant. All repository properties (except ``tenants``,
which is global for slug resolution / organization lookup) filter by that tenant
automatically. Write use cases wrap their work in ``with uow: ... uow.commit()`` so that
multi-aggregate operations (e.g. signing a consultation) are atomic.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date, datetime
from types import TracebackType
from typing import Protocol, runtime_checkable

from medicore.domain.entities.error_event import ErrorEvent
from medicore.domain.entities.job_run import JobRun
from medicore.domain.repositories import (
    AddonPricingRepository,
    ApplicationRepository,
    AppointmentRepository,
    AuditLogRepository,
    AuthSessionRepository,
    ConsultationRepository,
    DoctorAvailabilityRepository,
    DoctorProfileRepository,
    FeeScheduleRepository,
    InsurerRepository,
    MedicalCertificateRepository,
    MedicalDocumentRepository,
    MedicalRecordRepository,
    NotificationRepository,
    PatientRepository,
    PlanRepository,
    PlatformAdminRepository,
    PlatformAuditLogRepository,
    PrescriptionRepository,
    ProcedureRepository,
    RolePermissionOverrideRepository,
    SubscriptionPaymentRepository,
    TenantRepository,
    UserRepository,
    VaccinationRecordRepository,
)
from medicore.domain.repositories._support import (
    ActiveImpersonation,
    ApplicationReportRow,
    AppointmentFact,
    AppointmentReportRow,
    ConnectionStats,
    ConsoleLogin,
    DatabaseStatus,
    ErrorGroup,
    JobSummary,
    LoginPressure,
    Page,
    PaymentSummary,
    ProcedureFact,
    ProcedureReportRow,
    RequestStatsRow,
    TableSize,
    TenantActivity,
    VaccinationReportRow,
)
from medicore.domain.shared.identifiers import PatientId, TenantId, UserId


@runtime_checkable
class UnitOfWork(Protocol):
    tenant_id: TenantId

    patients: PatientRepository
    insurers: InsurerRepository
    appointments: AppointmentRepository
    consultations: ConsultationRepository
    medical_records: MedicalRecordRepository
    prescriptions: PrescriptionRepository
    documents: MedicalDocumentRepository
    certificates: MedicalCertificateRepository
    availability: DoctorAvailabilityRepository
    fees: FeeScheduleRepository
    users: UserRepository
    doctor_profiles: DoctorProfileRepository
    notifications: NotificationRepository
    audit: AuditLogRepository
    role_permissions: RolePermissionOverrideRepository
    vaccinations: VaccinationRecordRepository
    applications: ApplicationRepository
    procedures: ProcedureRepository
    subscription_payments: SubscriptionPaymentRepository
    tenants: TenantRepository  # global (not tenant-filtered)
    platform_audit: PlatformAuditLogRepository  # global (not tenant-filtered)
    sessions: AuthSessionRepository  # global (not tenant-filtered)
    plans: PlanRepository  # global subscription catalog
    addon_pricing: AddonPricingRepository  # global subscription catalog
    analytics: AnalyticsReadModel  # practice metrics (read-only)
    reports: ReportReadModel  # exportable reports (read-only)

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class AnalyticsReadModel(Protocol):
    """Tenant-scoped reads behind the clinic's metrics. ``doctor_id`` narrows everything to
    one doctor's appointments (None: the whole clinic)."""

    def appointment_facts(
        self, start: datetime, end: datetime, doctor_id: UserId | None = None
    ) -> list[AppointmentFact]:
        """Appointments starting in ``[start, end)`` (clinic wall-clock), any status."""
        ...

    def first_visits(
        self, patient_ids: list[PatientId], doctor_id: UserId | None = None
    ) -> dict[PatientId, datetime]:
        """Start of each patient's first completed appointment (omits those without one)."""
        ...

    def procedure_facts(
        self, since: datetime, until: datetime, doctor_id: UserId | None = None
    ) -> list[ProcedureFact]:
        """Completed procedures performed in ``[since, until)`` (instants), by ordering
        doctor."""
        ...

    def vaccinations_recorded(
        self, first: date, last: date, user_id: UserId | None = None
    ) -> int:
        """Vaccines given between ``first`` and ``last`` (inclusive), voided ones excluded."""
        ...

    def applications_recorded(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> int:
        """Doses applied in ``[since, until)`` (instants), voided or refused ones excluded."""
        ...


class ReportReadModel(Protocol):
    """Tenant-scoped rows behind the clinic's reports. ``user_id`` narrows each report to
    one person: the appointment's doctor, the procedure's ordering doctor, or whoever
    recorded the dose (None: the whole clinic)."""

    def appointment_rows(
        self, start: datetime, end: datetime, user_id: UserId | None = None
    ) -> list[AppointmentReportRow]:
        """Appointments starting in ``[start, end)`` (clinic wall-clock), any status,
        oldest first."""
        ...

    def procedure_rows(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> list[ProcedureReportRow]:
        """Completed procedures performed in ``[since, until)`` (instants), oldest first."""
        ...

    def vaccination_rows(
        self, first: date, last: date, user_id: UserId | None = None
    ) -> list[VaccinationReportRow]:
        """Doses administered at the clinic between ``first`` and ``last`` (inclusive),
        voided ones and records of doses given elsewhere excluded, oldest first."""
        ...

    def application_rows(
        self, since: datetime, until: datetime, user_id: UserId | None = None
    ) -> list[ApplicationReportRow]:
        """Doses applied in ``[since, until)`` (instants), voided or refused ones excluded,
        oldest first."""
        ...


@runtime_checkable
class PlatformUnitOfWork(Protocol):
    """Non-tenant-scoped transactional boundary for superadmin operations."""

    tenants: TenantRepository
    platform_admins: PlatformAdminRepository
    platform_audit: PlatformAuditLogRepository
    sessions: AuthSessionRepository
    plans: PlanRepository
    addon_pricing: AddonPricingRepository

    def __enter__(self) -> PlatformUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class PlatformReadModel(Protocol):
    """Cross-tenant read model for superadmin stats and the global audit viewer."""

    def tenant_counts(self, tenant_id: TenantId) -> dict[str, int]: ...

    def global_audit(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        tenant_id: str | None = None,
    ) -> list: ...

    # ── Business overview ──────────────────────────────────────────────────────

    def active_staff_by_tenant(self) -> dict[str, dict[str, int]]:
        """Active users per clinic and role (``{tenant_id: {role: n}}``)."""
        ...

    def payments_since(self, day: date) -> list[PaymentSummary]:
        """Subscription payments of every clinic paid on or after ``day``."""
        ...

    def activity_by_tenant(
        self, active_since: datetime, signed_since: datetime
    ) -> dict[str, TenantActivity]: ...

    def signed_per_week(self, since: datetime) -> list[tuple[date, int]]:
        """Records signed across every clinic, per ISO week (Monday), oldest first."""
        ...


class DiagnosisCatalogRepository(Protocol):
    """Global ICD/CIE catalog used for diagnosis autocomplete (not tenant-scoped)."""

    def search(self, version: str, query: str, limit: int = 20) -> list: ...

    def count(self, version: str) -> int: ...

    def upsert(self, entry) -> None: ...


class LoginThrottleRepository(Protocol):
    """Global failed-login counter with temporary lockout (not tenant-scoped).

    Implementations persist each mutation immediately (own commit): the recorded failure
    must survive the ``AuthenticationFailed`` raised right after it.
    """

    def locked_until(self, identifier: str, now: datetime) -> datetime | None:
        """Active lockout deadline for ``identifier``, or None when login may proceed."""
        ...

    def record_failure(self, identifier: str, now: datetime) -> datetime | None:
        """Count one failure; returns the lockout deadline when the threshold is crossed."""
        ...

    def reset(self, identifier: str) -> None:
        """Forget the failure history (called on successful login)."""
        ...

    def purge_stale(self, now: datetime) -> None:
        """Drop entries that no longer affect anything: last failure outside the window and
        no active lockout (the next failure would restart at 1 anyway). Run on successful
        logins, so identifiers that failed and never came back don't pile up."""
        ...


class MonitoringReadModel(Protocol):
    """System health for the platform console: database, sign-in pressure, live sessions
    and recorded server errors. Read-only, global (not tenant-scoped)."""

    def ping(self) -> None:
        """Round-trip to the database; raises when it is unreachable."""
        ...

    def database(self) -> DatabaseStatus: ...

    def largest_tables(self, limit: int) -> list[TableSize]: ...

    def login_pressure(self, since: datetime, now: datetime) -> LoginPressure:
        """Accounts failing to sign in since ``since`` and the lockouts active at ``now``."""
        ...

    def lockouts_since(self, since: datetime) -> int:
        """Lockouts of real accounts (clinic and console) recorded since ``since``."""
        ...

    def console_logins(self, limit: int) -> list[ConsoleLogin]:
        """Latest console sign-ins (successful, failed, locked), newest first."""
        ...

    def connections(self) -> ConnectionStats:
        """Database connections in use, by state, against the server's limit."""
        ...

    def sessions_by_kind(self, now: datetime) -> dict[str, int]:
        """Live sessions per kind: ``tenant``, ``support`` (impersonation) and ``platform``."""
        ...

    def active_impersonations(self, now: datetime) -> list[ActiveImpersonation]: ...

    def errors_since(self, since: datetime) -> int: ...

    def error_groups(self, since: datetime, limit: int) -> list[ErrorGroup]:
        """Errors since ``since`` grouped by route, type and location, most frequent first."""
        ...

    def recent_errors(self, limit: int, offset: int) -> Page[ErrorEvent]: ...

    def errors_per_day(self, since: datetime) -> list[tuple[date, int]]:
        """Errors per UTC day since ``since``, oldest first (days without errors omitted)."""
        ...

    def job_summaries(self) -> list[JobSummary]:
        """Latest run and latest success of every scheduled task that has ever run."""
        ...

    def request_stats_since(self, since: datetime) -> list[RequestStatsRow]:
        """Hourly request metrics per route from ``since`` on (summed across workers)."""
        ...


class ErrorLogRepository(Protocol):
    """Store of unexpected server errors. Each mutation commits on its own: it runs from the
    error handler, outside any request transaction (which has just failed)."""

    def record(self, event: ErrorEvent) -> None: ...

    def purge_before(self, cutoff: datetime) -> None:
        """Drop events older than ``cutoff`` (retention)."""
        ...


class JobLogRepository(Protocol):
    """Store of scheduled-task runs. Each mutation commits on its own (a run is recorded even
    when the task itself failed and rolled back)."""

    def record(self, run: JobRun) -> None: ...

    def purge_before(self, cutoff: datetime) -> None: ...


class RequestStatsRepository(Protocol):
    """Hourly request metrics per route. ``add`` sums a batch into the stored rows (several
    workers flush into the same hour); each mutation commits on its own."""

    def add(self, rows: list[RequestStatsRow]) -> None: ...

    def purge_before(self, cutoff: datetime) -> None: ...


class UnitOfWorkFactory(Protocol):
    def for_tenant(self, tenant_id: TenantId) -> UnitOfWork:
        """Build a UnitOfWork scoped to ``tenant_id``."""
        ...

    def global_tenants(self) -> AbstractContextManager[TenantRepository]:
        """Context-managed non-scoped tenant repository, used to resolve a tenant by slug
        before auth. The underlying session is closed on exit."""
        ...

    def platform_uow(self) -> PlatformUnitOfWork:
        """Build a non-tenant-scoped UnitOfWork for superadmin operations."""
        ...

    def platform_reads(self) -> AbstractContextManager[PlatformReadModel]:
        """Context-managed cross-tenant read model for superadmin stats and global audit."""
        ...

    def diagnosis_catalog(self) -> AbstractContextManager[DiagnosisCatalogRepository]:
        """Context-managed global ICD/CIE catalog repository for diagnosis autocomplete."""
        ...

    def login_throttle(self) -> AbstractContextManager[LoginThrottleRepository]:
        """Context-managed global login-attempt throttle used by the login use cases."""
        ...

    def monitoring_reads(self) -> AbstractContextManager[MonitoringReadModel]:
        """Context-managed system-health read model for the platform console."""
        ...

    def error_log(self) -> AbstractContextManager[ErrorLogRepository]:
        """Context-managed store of unexpected server errors."""
        ...

    def job_log(self) -> AbstractContextManager[JobLogRepository]:
        """Context-managed store of scheduled-task runs."""
        ...

    def request_stats(self) -> AbstractContextManager[RequestStatsRepository]:
        """Context-managed store of hourly request metrics."""
        ...
