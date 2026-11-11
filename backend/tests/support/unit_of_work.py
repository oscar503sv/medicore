"""In-memory UnitOfWork with real snapshot/rollback transactional semantics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType

from medicore.domain.shared.identifiers import TenantId
from tests.support.repositories import (
    InMemoryAddonPricingRepository,
    InMemoryApplicationRepository,
    InMemoryAppointmentRepository,
    InMemoryAuditLogRepository,
    InMemoryAuthSessionRepository,
    InMemoryConsultationRepository,
    InMemoryDiagnosisCatalogRepository,
    InMemoryDoctorAvailabilityRepository,
    InMemoryDoctorProfileRepository,
    InMemoryErrorLogRepository,
    InMemoryFeeScheduleRepository,
    InMemoryInsurerRepository,
    InMemoryJobLogRepository,
    InMemoryLoginThrottleRepository,
    InMemoryMedicalDocumentRepository,
    InMemoryMedicalRecordRepository,
    InMemoryMonitoringReadModel,
    InMemoryNotificationRepository,
    InMemoryPatientRepository,
    InMemoryPlanRepository,
    InMemoryPlatformAdminRepository,
    InMemoryPlatformAuditLogRepository,
    InMemoryPlatformReadModel,
    InMemoryPrescriptionRepository,
    InMemoryProcedureRepository,
    InMemoryRequestStatsRepository,
    InMemoryRolePermissionOverrideRepository,
    InMemorySubscriptionPaymentRepository,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryVaccinationRecordRepository,
)
from tests.support.store import InMemoryStore


class InMemoryUnitOfWork:
    """Bound to one tenant. ``with uow:`` snapshots the store; an exception or a missing
    ``commit()`` restores it, giving the SignConsultation transaction true atomicity."""

    def __init__(self, store: InMemoryStore, tenant_id: TenantId) -> None:
        self._store = store
        self.tenant_id = tenant_id
        self.patients = InMemoryPatientRepository(store, tenant_id)
        self.insurers = InMemoryInsurerRepository(store, tenant_id)
        self.appointments = InMemoryAppointmentRepository(store, tenant_id)
        self.consultations = InMemoryConsultationRepository(store, tenant_id)
        self.medical_records = InMemoryMedicalRecordRepository(store, tenant_id)
        self.prescriptions = InMemoryPrescriptionRepository(store, tenant_id)
        self.documents = InMemoryMedicalDocumentRepository(store, tenant_id)
        self.availability = InMemoryDoctorAvailabilityRepository(store, tenant_id)
        self.fees = InMemoryFeeScheduleRepository(store, tenant_id)
        self.users = InMemoryUserRepository(store, tenant_id)
        self.doctor_profiles = InMemoryDoctorProfileRepository(store, tenant_id)
        self.notifications = InMemoryNotificationRepository(store, tenant_id)
        self.audit = InMemoryAuditLogRepository(store, tenant_id)
        self.role_permissions = InMemoryRolePermissionOverrideRepository(store, tenant_id)
        self.vaccinations = InMemoryVaccinationRecordRepository(store, tenant_id)
        self.applications = InMemoryApplicationRepository(store, tenant_id)
        self.procedures = InMemoryProcedureRepository(store, tenant_id)
        self.subscription_payments = InMemorySubscriptionPaymentRepository(store, tenant_id)
        self.tenants = InMemoryTenantRepository(store)
        self.platform_audit = InMemoryPlatformAuditLogRepository(store)
        self.sessions = InMemoryAuthSessionRepository(store)
        self.plans = InMemoryPlanRepository(store)
        self.addon_pricing = InMemoryAddonPricingRepository(store)
        self._snapshot: dict | None = None
        self._committed = False

    def __enter__(self) -> InMemoryUnitOfWork:
        self._snapshot = self._store.snapshot()
        self._committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if (exc_type is not None or not self._committed) and self._snapshot is not None:
            self._store.restore(self._snapshot)
        self._snapshot = None
        return False  # never suppress exceptions

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        if self._snapshot is not None:
            self._store.restore(self._snapshot)
        self._committed = False


class InMemoryPlatformUnitOfWork:
    """Non-tenant-scoped UoW for superadmin operations, with snapshot/rollback semantics."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self.tenants = InMemoryTenantRepository(store)
        self.platform_admins = InMemoryPlatformAdminRepository(store)
        self.platform_audit = InMemoryPlatformAuditLogRepository(store)
        self.sessions = InMemoryAuthSessionRepository(store)
        self.plans = InMemoryPlanRepository(store)
        self.addon_pricing = InMemoryAddonPricingRepository(store)
        self._snapshot: dict | None = None
        self._committed = False

    def __enter__(self) -> InMemoryPlatformUnitOfWork:
        self._snapshot = self._store.snapshot()
        self._committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if (exc_type is not None or not self._committed) and self._snapshot is not None:
            self._store.restore(self._snapshot)
        self._snapshot = None
        return False

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        if self._snapshot is not None:
            self._store.restore(self._snapshot)
        self._committed = False


class InMemoryUnitOfWorkFactory:
    def __init__(self, store: InMemoryStore | None = None) -> None:
        self.store = store or InMemoryStore()

    def for_tenant(self, tenant_id: TenantId) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self.store, tenant_id)

    @contextmanager
    def global_tenants(self) -> Iterator[InMemoryTenantRepository]:
        yield InMemoryTenantRepository(self.store)

    def platform_uow(self) -> InMemoryPlatformUnitOfWork:
        return InMemoryPlatformUnitOfWork(self.store)

    @contextmanager
    def platform_admins(self) -> Iterator[InMemoryPlatformAdminRepository]:
        yield InMemoryPlatformAdminRepository(self.store)

    @contextmanager
    def platform_reads(self) -> Iterator[InMemoryPlatformReadModel]:
        yield InMemoryPlatformReadModel(self.store)

    @contextmanager
    def diagnosis_catalog(self) -> Iterator[InMemoryDiagnosisCatalogRepository]:
        yield InMemoryDiagnosisCatalogRepository(self.store)

    @contextmanager
    def login_throttle(self) -> Iterator[InMemoryLoginThrottleRepository]:
        yield InMemoryLoginThrottleRepository(self.store)

    @contextmanager
    def monitoring_reads(self) -> Iterator[InMemoryMonitoringReadModel]:
        yield InMemoryMonitoringReadModel(self.store)

    @contextmanager
    def error_log(self) -> Iterator[InMemoryErrorLogRepository]:
        yield InMemoryErrorLogRepository(self.store)

    @contextmanager
    def job_log(self) -> Iterator[InMemoryJobLogRepository]:
        yield InMemoryJobLogRepository(self.store)

    @contextmanager
    def request_stats(self) -> Iterator[InMemoryRequestStatsRepository]:
        yield InMemoryRequestStatsRepository(self.store)
