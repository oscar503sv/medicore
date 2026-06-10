"""Tests for the patient archive/reactivate lifecycle."""

from __future__ import annotations

from medicore.application.use_cases.patients import ArchivePatient, ReactivatePatient
from medicore.domain.enums import PatientStatus
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock


class TestPatientLifecycle:
    def test_archive_then_reactivate_restores_active(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        actor = seed.actor(seed.admin)

        archived = ArchivePatient(uow, FixedClock()).execute(actor, seed.patient.id)
        assert archived.status is PatientStatus.INACTIVE

        restored = ReactivatePatient(uow, FixedClock()).execute(actor, seed.patient.id)
        assert restored.status is PatientStatus.ACTIVE
        assert uow.patients.get_by_id(seed.patient.id).status is PatientStatus.ACTIVE
        assert uow.audit.query(action="patient.reactivated")
