"""Tests for the insurer catalog use cases (admin-managed; everyone may list)."""

from __future__ import annotations

from datetime import datetime

import pytest

from medicore.application.use_cases.appointments import (
    CreateAppointment,
    CreateAppointmentCommand,
)
from medicore.application.use_cases.insurers import (
    ArchiveInsurer,
    CreateInsurer,
    CreateInsurerCommand,
    ListInsurers,
    ReactivateInsurer,
    UpdateInsurer,
)
from medicore.domain.enums import AppointmentType
from medicore.domain.shared.errors import PermissionDenied
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, SequentialCodeGenerator


def _make_insurer(seed, uow, name="Sanitas"):
    return CreateInsurer(uow, FixedClock()).execute(
        seed.actor(seed.admin),
        CreateInsurerCommand(name=name, phone="900100100", address="Calle 1"),
    )


class TestInsurerManagement:
    def test_admin_creates_insurer_and_audits(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        insurer = _make_insurer(seed, uow)
        assert insurer.active is True
        assert insurer.name == "Sanitas"
        assert uow.audit.query(action="insurer.created")
        assert [i.name for i in ListInsurers(uow).execute(seed.actor(seed.admin))] == ["Sanitas"]

    def test_non_admin_cannot_create(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            CreateInsurer(uow, FixedClock()).execute(
                seed.receptionist_actor, CreateInsurerCommand(name="Adeslas")
            )

    def test_anyone_may_list(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        _make_insurer(seed, uow)
        # Receptionist (registers patients) must be able to read the catalog.
        names = [i.name for i in ListInsurers(uow).execute(seed.receptionist_actor)]
        assert names == ["Sanitas"]

    def test_update_insurer(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        insurer = _make_insurer(seed, uow)
        updated = UpdateInsurer(uow, FixedClock()).execute(
            seed.actor(seed.admin), insurer.id, phone="611223344", contact_person="Ana"
        )
        assert updated.phone == "611223344"
        assert updated.contact_person == "Ana"

    def test_archive_hides_from_active_only(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        insurer = _make_insurer(seed, uow)
        ArchiveInsurer(uow, FixedClock()).execute(seed.actor(seed.admin), insurer.id)
        assert ListInsurers(uow).execute(seed.actor(seed.admin), active_only=True) == []
        assert len(ListInsurers(uow).execute(seed.actor(seed.admin))) == 1

    def test_reactivate_restores_to_active_only(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        insurer = _make_insurer(seed, uow)
        ArchiveInsurer(uow, FixedClock()).execute(seed.actor(seed.admin), insurer.id)
        restored = ReactivateInsurer(uow, FixedClock()).execute(
            seed.actor(seed.admin), insurer.id
        )
        assert restored.active is True
        active = ListInsurers(uow).execute(seed.actor(seed.admin), active_only=True)
        assert [i.name for i in active] == ["Sanitas"]
        assert uow.audit.query(action="insurer.reactivated")

    def test_non_admin_cannot_reactivate(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        insurer = _make_insurer(seed, uow)
        with pytest.raises(PermissionDenied):
            ReactivateInsurer(uow, FixedClock()).execute(seed.receptionist_actor, insurer.id)


class TestAppointmentInsurerLink:
    def test_appointment_create_round_trips_insurance_id(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        insurer = _make_insurer(seed, uow)
        appt = CreateAppointment(uow, SequentialCodeGenerator(), FixedClock()).execute(
            seed.receptionist_actor,
            CreateAppointmentCommand(
                patient_id=seed.patient.id,
                doctor_id=seed.doctor.id,
                location_id=seed.tenant.primary_location.id,
                type=AppointmentType.CONSULT,
                scheduled_start=datetime(2026, 6, 1, 9, 0),  # within Mon 09:00–13:00
                reason="Consulta con seguro",
                insurance_id=insurer.id,
            ),
        )
        assert appt.insurance_id == insurer.id
        reloaded = uow.appointments.get_by_id(appt.id)
        assert reloaded.insurance_id == insurer.id

    def test_appointment_without_insurance_is_private(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        appt = CreateAppointment(uow, SequentialCodeGenerator(), FixedClock()).execute(
            seed.receptionist_actor,
            CreateAppointmentCommand(
                patient_id=seed.patient.id,
                doctor_id=seed.doctor.id,
                location_id=seed.tenant.primary_location.id,
                type=AppointmentType.CONSULT,
                scheduled_start=datetime(2026, 6, 1, 10, 0),
                reason="Consulta privada",
            ),
        )
        assert appt.insurance_id is None
