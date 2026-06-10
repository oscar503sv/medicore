"""The permission catalog is the authorization contract: this matrix is the spec.

The snapshot below is written out as literal data (NOT derived from ROLE_PERMISSIONS) so
that any change to a role's grants — accidental or deliberate — fails here and forces the
matrix to be updated consciously.
"""

from __future__ import annotations

import pytest

from medicore.application.common.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    ensure_permission,
    has_permission,
    permissions_for,
)
from medicore.application.use_cases.consultations import StartConsultation
from medicore.application.use_cases.patients import ArchivePatient, UpdatePatient
from medicore.domain.enums import Role
from medicore.domain.shared.errors import PermissionDenied
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock

EXPECTED_MATRIX: dict[Role, set[str]] = {
    Role.ADMIN: {
        "patients.view", "patients.create", "patients.edit", "patients.archive",
        "appointments.view", "appointments.manage",
        "availability.manage",
        "consultations.start", "consultations.edit",
        "records.view", "records.upload",
        "diagnoses.view",
        "insurers.view", "insurers.manage",
        "users.view", "users.manage",
        "organization.view", "organization.manage",
        "audit.view",
        "permissions.manage",
    },
    Role.DOCTOR: {
        "patients.view", "patients.create", "patients.edit", "patients.archive",
        "appointments.view", "appointments.manage",
        "availability.manage",
        "consultations.start", "consultations.edit",
        "records.view", "records.upload", "records.sign", "records.amend",
        "diagnoses.view",
        "insurers.view",
    },
    Role.NURSE: {
        "patients.view", "patients.create",
        "appointments.view",
        "consultations.edit",
        "records.view", "records.upload",
        "diagnoses.view",
        "insurers.view",
    },
    Role.RECEPTIONIST: {
        "patients.view", "patients.create", "patients.edit", "patients.archive",
        "appointments.view", "appointments.manage",
        "diagnoses.view",
        "insurers.view",
    },
}


class TestCatalog:
    def test_matrix_snapshot(self):
        actual = {role: {str(p) for p in perms} for role, perms in ROLE_PERMISSIONS.items()}
        assert actual == EXPECTED_MATRIX

    def test_every_role_is_mapped(self):
        assert set(ROLE_PERMISSIONS) == set(Role)

    def test_every_permission_is_granted_to_someone(self):
        granted = frozenset().union(*ROLE_PERMISSIONS.values())
        assert granted == frozenset(Permission)

    def test_permissions_for_matches_map(self):
        for role in Role:
            assert permissions_for(role) == ROLE_PERMISSIONS[role]


class TestEnforcement:
    def test_ensure_permission_passes_when_granted(self):
        seed = seed_clinic()
        ensure_permission(seed.doctor_actor, Permission.RECORDS_SIGN)

    def test_ensure_permission_raises_when_missing(self):
        seed = seed_clinic()
        with pytest.raises(PermissionDenied):
            ensure_permission(seed.actor(seed.nurse), Permission.RECORDS_SIGN)

    def test_has_permission(self):
        seed = seed_clinic()
        assert has_permission(seed.receptionist_actor, Permission.APPOINTMENTS_MANAGE)
        assert not has_permission(seed.receptionist_actor, Permission.RECORDS_VIEW)


class TestTightenedGrants:
    """Deliberate hardenings vs the old role checks: nurses no longer edit/archive
    patients nor open consultations (the UI never offered it; the API now agrees)."""

    def test_nurse_cannot_update_patient(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            UpdatePatient(uow, FixedClock()).execute(
                seed.actor(seed.nurse), seed.patient.id, first_name="X"
            )

    def test_nurse_cannot_archive_patient(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            ArchivePatient(uow, FixedClock()).execute(seed.actor(seed.nurse), seed.patient.id)

    def test_nurse_cannot_start_consultation(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            StartConsultation(uow, FixedClock()).execute(seed.actor(seed.nurse), object())
