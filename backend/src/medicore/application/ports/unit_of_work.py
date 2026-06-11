"""UnitOfWork port — a transactional boundary that exposes the tenant-scoped repositories.

A UnitOfWork is bound to a single tenant. All repository properties (except ``tenants``,
which is global for slug resolution / organization lookup) filter by that tenant
automatically. Write use cases wrap their work in ``with uow: ... uow.commit()`` so that
multi-aggregate operations (e.g. signing a consultation) are atomic.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from types import TracebackType
from typing import Protocol, runtime_checkable

from medicore.domain.repositories import (
    AppointmentRepository,
    AuditLogRepository,
    AuthSessionRepository,
    ConsultationRepository,
    DoctorAvailabilityRepository,
    DoctorProfileRepository,
    InsurerRepository,
    MedicalDocumentRepository,
    MedicalRecordRepository,
    NotificationRepository,
    PatientRepository,
    PlatformAdminRepository,
    PlatformAuditLogRepository,
    PrescriptionRepository,
    RolePermissionOverrideRepository,
    TenantRepository,
    UserRepository,
)
from medicore.domain.shared.identifiers import TenantId


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
    availability: DoctorAvailabilityRepository
    users: UserRepository
    doctor_profiles: DoctorProfileRepository
    notifications: NotificationRepository
    audit: AuditLogRepository
    role_permissions: RolePermissionOverrideRepository
    tenants: TenantRepository  # global (not tenant-filtered)
    platform_audit: PlatformAuditLogRepository  # global (not tenant-filtered)
    sessions: AuthSessionRepository  # global (not tenant-filtered)

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class PlatformUnitOfWork(Protocol):
    """Non-tenant-scoped transactional boundary for superadmin operations."""

    tenants: TenantRepository
    platform_admins: PlatformAdminRepository
    platform_audit: PlatformAuditLogRepository
    sessions: AuthSessionRepository

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

    def counts_by_tenant(self) -> dict[str, dict[str, int]]: ...

    def tenant_counts(self, tenant_id: TenantId) -> dict[str, int]: ...

    def global_audit(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        tenant_id: str | None = None,
    ) -> list: ...


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
