"""UnitOfWork port — a transactional boundary that exposes the tenant-scoped repositories.

A UnitOfWork is bound to a single tenant. All repository properties (except ``tenants``,
which is global for slug resolution / organization lookup) filter by that tenant
automatically. Write use cases wrap their work in ``with uow: ... uow.commit()`` so that
multi-aggregate operations (e.g. signing a consultation) are atomic.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable

from medicore.domain.repositories import (
    AppointmentRepository,
    AuditLogRepository,
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
    tenants: TenantRepository  # global (not tenant-filtered)
    platform_audit: PlatformAuditLogRepository  # global (not tenant-filtered)

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

    def __enter__(self) -> PlatformUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def for_tenant(self, tenant_id: TenantId) -> UnitOfWork:
        """Build a UnitOfWork scoped to ``tenant_id``."""
        ...

    def global_tenants(self) -> TenantRepository:
        """The non-scoped tenant repository, used to resolve a tenant by slug before auth."""
        ...

    def platform_uow(self) -> PlatformUnitOfWork:
        """Build a non-tenant-scoped UnitOfWork for superadmin operations."""
        ...
