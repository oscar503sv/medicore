"""SQLAlchemy UnitOfWork — the real transactional boundary for the application layer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType

from sqlalchemy.orm import Session

from medicore.domain.shared.identifiers import TenantId
from medicore.infrastructure.persistence.repositories.appointment import SqlAppointmentRepository
from medicore.infrastructure.persistence.repositories.clinical import (
    SqlConsultationRepository,
    SqlMedicalDocumentRepository,
    SqlMedicalRecordRepository,
    SqlPrescriptionRepository,
)
from medicore.infrastructure.persistence.repositories.diagnosis_catalog import (
    SqlDiagnosisCatalogRepository,
)
from medicore.infrastructure.persistence.repositories.insurer import SqlInsurerRepository
from medicore.infrastructure.persistence.repositories.other import (
    SqlAuditLogRepository,
    SqlDoctorAvailabilityRepository,
    SqlNotificationRepository,
)
from medicore.infrastructure.persistence.repositories.patient import SqlPatientRepository
from medicore.infrastructure.persistence.repositories.platform import (
    SqlPlatformAdminRepository,
    SqlPlatformAuditLogRepository,
)
from medicore.infrastructure.persistence.repositories.platform_reads import SqlPlatformReadModel
from medicore.infrastructure.persistence.repositories.role_permission_override import (
    SqlRolePermissionOverrideRepository,
)
from medicore.infrastructure.persistence.repositories.tenant import SqlTenantRepository
from medicore.infrastructure.persistence.repositories.user import (
    SqlDoctorProfileRepository,
    SqlUserRepository,
)


class SqlAlchemyUnitOfWork:
    """One session per UoW; ``with uow:`` begins an implicit transaction.
    ``commit()`` flushes and commits; any exception or omission of ``commit()`` rolls back.
    """

    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._session = session
        self.tenant_id = tenant_id

        self.patients = SqlPatientRepository(session, tenant_id)
        self.insurers = SqlInsurerRepository(session, tenant_id)
        self.appointments = SqlAppointmentRepository(session, tenant_id)
        self.consultations = SqlConsultationRepository(session, tenant_id)
        self.medical_records = SqlMedicalRecordRepository(session, tenant_id)
        self.prescriptions = SqlPrescriptionRepository(session, tenant_id)
        self.documents = SqlMedicalDocumentRepository(session, tenant_id)
        self.availability = SqlDoctorAvailabilityRepository(session, tenant_id)
        self.users = SqlUserRepository(session, tenant_id)
        self.doctor_profiles = SqlDoctorProfileRepository(session, tenant_id)
        self.notifications = SqlNotificationRepository(session, tenant_id)
        self.audit = SqlAuditLogRepository(session, tenant_id)
        self.role_permissions = SqlRolePermissionOverrideRepository(session, tenant_id)
        self.tenants = SqlTenantRepository(session)  # global (non-scoped)
        self.platform_audit = SqlPlatformAuditLogRepository(session)  # global (non-scoped)

        self._committed = False

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self._committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        return False

    def commit(self) -> None:
        self._session.commit()
        self._committed = True

    def rollback(self) -> None:
        self._session.rollback()
        self._committed = False


class PlatformUnitOfWork:
    """A non-tenant-scoped transactional boundary for superadmin operations.

    Exposes only the global repositories a platform admin needs (tenants, platform admins and
    the platform audit trail). Tenant-targeting operations (creating a clinic's first user,
    resetting a password) use ``for_tenant`` instead.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self.tenants = SqlTenantRepository(session)
        self.platform_admins = SqlPlatformAdminRepository(session)
        self.platform_audit = SqlPlatformAuditLogRepository(session)
        self._committed = False

    def __enter__(self) -> PlatformUnitOfWork:
        self._committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        return False

    def commit(self) -> None:
        self._session.commit()
        self._committed = True

    def rollback(self) -> None:
        self._session.rollback()
        self._committed = False


class SqlAlchemyUnitOfWorkFactory:
    def __init__(self, session_factory) -> None:
        self._factory = session_factory

    def for_tenant(self, tenant_id: TenantId) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._factory(), tenant_id)

    @contextmanager
    def global_tenants(self) -> Iterator[SqlTenantRepository]:
        session = self._factory()
        try:
            yield SqlTenantRepository(session)
        finally:
            session.close()

    def platform_uow(self) -> PlatformUnitOfWork:
        return PlatformUnitOfWork(self._factory())

    @contextmanager
    def platform_admins(self) -> Iterator[SqlPlatformAdminRepository]:
        session = self._factory()
        try:
            yield SqlPlatformAdminRepository(session)
        finally:
            session.close()

    @contextmanager
    def platform_reads(self) -> Iterator[SqlPlatformReadModel]:
        session = self._factory()
        try:
            yield SqlPlatformReadModel(session)
        finally:
            session.close()

    @contextmanager
    def diagnosis_catalog(self) -> Iterator[SqlDiagnosisCatalogRepository]:
        session = self._factory()
        try:
            yield SqlDiagnosisCatalogRepository(session)
        finally:
            session.close()
