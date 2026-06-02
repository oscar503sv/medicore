"""Tests for the admin/doctor management use cases: users, availability, organization."""

from __future__ import annotations

from datetime import date, time

import pytest

from medicore.application.use_cases.availability import (
    AddAvailabilityException,
    GetMyAvailability,
    PreviewAvailability,
    UpdateBookingRules,
    UpdateWeeklySchedule,
)
from medicore.application.use_cases.organization import (
    AddLocation,
    GetOrganization,
    UpdateOrganization,
)
from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    ListUsers,
    ReactivateUser,
    ResetUserPassword,
    ResetUserPasswordCommand,
    SuspendUser,
    UpdateUser,
    UpdateUserRole,
)
from medicore.domain.entities.availability import (
    AvailabilityException,
    BookingRules,
    WeeklyDay,
)
from medicore.domain.enums import (
    AvailabilityExceptionKind,
    Role,
    UserStatus,
)
from medicore.domain.services.slot_resolver import SlotStatus
from medicore.domain.shared.errors import PermissionDenied
from medicore.domain.value_objects.time_range import TimeRange
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock, PlainPasswordHasher


class TestUsers:
    def test_admin_invites_user_active_with_temp_password(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        user = InviteUser(uow, PlainPasswordHasher(), FixedClock()).execute(
            seed.actor(seed.admin),
            InviteUserCommand(
                name="Nuevo",
                email="nuevo@clinica-norte.test",
                role=Role.NURSE,
                password="temporal123",
            ),
        )
        assert user.status == UserStatus.ACTIVE
        assert user.must_change_password is True
        assert user.password_hash  # a temp password was set
        assert uow.audit.query(action="user.invited")

    def test_invite_duplicate_email_rejected(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        from medicore.application.common.errors import ValidationError

        with pytest.raises(ValidationError):
            InviteUser(uow, PlainPasswordHasher(), FixedClock()).execute(
                seed.actor(seed.admin),
                InviteUserCommand(
                    name="Dup",
                    email=seed.doctor.email,
                    role=Role.DOCTOR,
                    password="temporal123",
                ),
            )

    def test_non_admin_cannot_manage_users(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            ListUsers(uow).execute(seed.receptionist_actor)

    def test_update_role_and_suspend(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        UpdateUserRole(uow, FixedClock()).execute(admin, seed.nurse.id, Role.RECEPTIONIST)
        assert uow.users.get_by_id(seed.nurse.id).role == Role.RECEPTIONIST
        SuspendUser(uow, FixedClock()).execute(admin, seed.nurse.id)
        assert uow.users.get_by_id(seed.nurse.id).status == UserStatus.SUSPENDED

    def test_update_user_edits_profile_fields(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        UpdateUser(uow, FixedClock()).execute(
            admin,
            seed.nurse.id,
            name="Nombre Nuevo",
            role=Role.RECEPTIONIST,
            phone="611223344",
            specialty="Triage",
        )
        updated = uow.users.get_by_id(seed.nurse.id)
        assert updated.name == "Nombre Nuevo"
        assert updated.role == Role.RECEPTIONIST
        assert updated.phone == "611223344"
        assert updated.specialty == "Triage"
        assert uow.audit.query(action="user.updated")

    def test_suspend_then_reactivate(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        SuspendUser(uow, FixedClock()).execute(admin, seed.nurse.id)
        ReactivateUser(uow, FixedClock()).execute(admin, seed.nurse.id)
        assert uow.users.get_by_id(seed.nurse.id).status == UserStatus.ACTIVE
        assert uow.audit.query(action="user.reactivated")

    def test_reset_password_sets_temp_and_forces_change(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        hasher = PlainPasswordHasher()
        ResetUserPassword(uow, hasher, FixedClock()).execute(
            seed.actor(seed.admin),
            ResetUserPasswordCommand(user_id=seed.nurse.id, password="nuevaTemp1"),
        )
        reloaded = uow.users.get_by_id(seed.nurse.id)
        assert reloaded.must_change_password is True
        assert hasher.verify("nuevaTemp1", reloaded.password_hash)
        assert uow.audit.query(action="user.password_reset")

    def test_non_admin_cannot_reset_password(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            ResetUserPassword(uow, PlainPasswordHasher(), FixedClock()).execute(
                seed.receptionist_actor,
                ResetUserPasswordCommand(user_id=seed.nurse.id, password="nuevaTemp1"),
            )


class TestAvailability:
    def test_get_my_availability_returns_existing(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        availability = GetMyAvailability(uow).execute(seed.doctor_actor)
        assert availability.doctor_id == seed.doctor.id

    def test_update_weekly_schedule_persists(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        saturday = WeeklyDay(
            day_of_week=5, enabled=True, blocks=[TimeRange(time(10, 0), time(12, 0))]
        )
        UpdateWeeklySchedule(uow, FixedClock()).execute(seed.doctor_actor, [saturday])
        stored = uow.availability.get_by_doctor(seed.doctor.id)
        assert stored.day(5).enabled

    def test_add_exception_and_update_rules(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        AddAvailabilityException(uow, FixedClock()).execute(
            seed.doctor_actor,
            AvailabilityException(
                id=_exception_id(),
                date=date(2026, 6, 8),
                kind=AvailabilityExceptionKind.OFF,
                reason="Congreso",
            ),
        )
        UpdateBookingRules(uow, FixedClock()).execute(
            seed.doctor_actor, BookingRules(slot_minutes=20, buffer_minutes=5)
        )
        stored = uow.availability.get_by_doctor(seed.doctor.id)
        assert stored.exception_on(date(2026, 6, 8)) is not None
        assert stored.rules.slot_minutes == 20

    def test_preview_returns_seven_days(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        preview = PreviewAvailability(uow, FixedClock()).execute(
            seed.doctor_actor, date(2026, 6, 1)
        )
        assert len(preview) == 7
        # The preview paints the full daily grid; Monday's 09:00–13:00 block → 8 free slots.
        monday = preview[date(2026, 6, 1)]
        assert len([s for s in monday if s.status == SlotStatus.FREE]) == 8

    def test_receptionist_cannot_manage_availability(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            GetMyAvailability(uow).execute(seed.receptionist_actor)


class TestOrganization:
    def test_get_and_update_organization(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        admin = seed.actor(seed.admin)
        org = GetOrganization(uow).execute(admin)
        assert org.id == seed.tenant.id
        UpdateOrganization(uow, FixedClock()).execute(admin, legal_name="Clínica Norte SLU")
        assert uow.tenants.get_by_id(seed.tenant.id).legal_name == "Clínica Norte SLU"

    def test_add_location(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        tenant = AddLocation(uow, FixedClock()).execute(
            seed.actor(seed.admin), name="Madrid · Salamanca", address="C/ Velázquez"
        )
        assert any(loc.name == "Madrid · Salamanca" for loc in tenant.locations)

    def test_non_admin_cannot_read_organization(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        with pytest.raises(PermissionDenied):
            GetOrganization(uow).execute(seed.doctor_actor)


def _exception_id():
    from medicore.domain.shared.identifiers import ExceptionId

    return ExceptionId.new()
