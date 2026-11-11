"""Tests for notification emission and the notification inbox use cases."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from medicore.application.common.errors import EntityNotFound
from medicore.application.common.notifications import (
    APPOINTMENT_CANCELLED,
    APPOINTMENT_CREATED,
    APPOINTMENT_NO_SHOW,
    APPOINTMENT_RESCHEDULED,
    DOCUMENT_UPLOADED,
    RECORD_AMENDED,
    USER_CREATED,
    USER_ROLE_CHANGED,
)
from medicore.application.use_cases.appointments import (
    CancelAppointment,
    ConfirmAppointment,
    CreateAppointment,
    MarkNoShow,
    RescheduleAppointment,
)
from medicore.application.use_cases.notifications import (
    CountMyUnreadNotifications,
    ListMyNotifications,
    MarkAllNotificationsRead,
    MarkNotificationRead,
)
from medicore.application.use_cases.records import AmendMedicalRecord, UploadDocument
from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    UpdateUser,
    UpdateUserRole,
)
from medicore.domain.entities.notification import Notification
from medicore.domain.enums import Role
from medicore.domain.repositories._support import Paging
from medicore.domain.shared.identifiers import NotificationId, PlatformAdminId
from tests.application.test_appointments import MONDAY_9AM, booking_cmd
from tests.application.test_records_and_permissions import _sign_a_record, _upload_cmd
from tests.support.builders import build_user, seed_clinic
from tests.support.fakes import FixedClock, PlainPasswordHasher, SequentialCodeGenerator


def _inbox(seed, user) -> list[Notification]:
    uow = seed.factory.for_tenant(seed.tenant.id)
    return uow.notifications.list_by_user(user.id)


def _book(seed, actor):
    uow = seed.factory.for_tenant(seed.tenant.id)
    return CreateAppointment(uow, SequentialCodeGenerator(), FixedClock()).execute(
        actor, booking_cmd(seed)
    )


class TestAppointmentNotifications:
    def test_booking_by_reception_notifies_the_doctor(self):
        seed = seed_clinic()
        appt = _book(seed, seed.receptionist_actor)

        [n] = _inbox(seed, seed.doctor)
        assert n.type == APPOINTMENT_CREATED
        assert n.data["appointment_id"] == str(appt.id)
        assert n.data["appointment_code"] == appt.code
        assert n.data["patient_id"] == str(seed.patient.id)
        assert n.data["patient_name"] == seed.patient.full_name
        assert n.data["scheduled_start"] == MONDAY_9AM.isoformat()
        assert n.data["actor_name"] == seed.receptionist.name
        assert not n.is_read

    def test_doctor_booking_their_own_appointment_is_not_notified(self):
        seed = seed_clinic()
        _book(seed, seed.doctor_actor)
        assert _inbox(seed, seed.doctor) == []

    def test_reschedule_carries_previous_start(self):
        seed = seed_clinic()
        appt = _book(seed, seed.doctor_actor)
        uow = seed.factory.for_tenant(seed.tenant.id)
        new_start = MONDAY_9AM + timedelta(hours=1)

        RescheduleAppointment(uow, FixedClock()).execute(
            seed.receptionist_actor, appt.id, new_start
        )

        [n] = _inbox(seed, seed.doctor)
        assert n.type == APPOINTMENT_RESCHEDULED
        assert n.data["scheduled_start"] == new_start.isoformat()
        assert n.data["previous_start"] == MONDAY_9AM.isoformat()

    @pytest.mark.parametrize(
        ("use_case", "expected"),
        [(CancelAppointment, APPOINTMENT_CANCELLED), (MarkNoShow, APPOINTMENT_NO_SHOW)],
    )
    def test_status_changes_notify_the_doctor(self, use_case, expected):
        seed = seed_clinic()
        appt = _book(seed, seed.doctor_actor)
        uow = seed.factory.for_tenant(seed.tenant.id)

        use_case(uow, FixedClock()).execute(seed.receptionist_actor, appt.id)

        assert [n.type for n in _inbox(seed, seed.doctor)] == [expected]

    def test_confirmation_is_not_notified(self):
        seed = seed_clinic()
        appt = _book(seed, seed.doctor_actor)
        uow = seed.factory.for_tenant(seed.tenant.id)

        ConfirmAppointment(uow, FixedClock()).execute(seed.receptionist_actor, appt.id)

        assert _inbox(seed, seed.doctor) == []


class TestRecordNotifications:
    def test_amendment_by_someone_else_notifies_the_original_author(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        original = _sign_a_record(seed, uow)
        colleague = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Colega", email="c@x.test")
        seed.factory.store.users[colleague.id.value] = colleague

        amendment = AmendMedicalRecord(uow, FixedClock()).execute(
            seed.actor(colleague), original.id, chief_complaint="Corregido"
        )

        [n] = _inbox(seed, seed.doctor)
        assert n.type == RECORD_AMENDED
        assert n.data["record_id"] == str(amendment.id)
        assert n.data["record_code"] == amendment.code
        assert n.data["patient_name"] == seed.patient.full_name
        assert n.data["actor_name"] == "Dr. Colega"
        # Clinical content never travels in a notification.
        assert "Corregido" not in n.data.values()

    def test_author_amending_their_own_record_is_not_notified(self):
        seed = seed_clinic()
        uow = seed.factory.for_tenant(seed.tenant.id)
        original = _sign_a_record(seed, uow)

        AmendMedicalRecord(uow, FixedClock()).execute(
            seed.doctor_actor, original.id, chief_complaint="Corregido"
        )

        assert _inbox(seed, seed.doctor) == []


class TestDocumentNotifications:
    def _upload(self, seed, actor):
        uow = seed.factory.for_tenant(seed.tenant.id)
        return UploadDocument(uow, FixedClock()).execute(actor, _upload_cmd(seed))

    def test_upload_notifies_the_assigned_doctor_without_the_file_name(self):
        seed = seed_clinic()  # the seeded patient is assigned to seed.doctor
        document = self._upload(seed, seed.actor(seed.nurse))

        [n] = _inbox(seed, seed.doctor)
        assert n.type == DOCUMENT_UPLOADED
        assert n.data["document_id"] == str(document.id)
        assert n.data["kind"] == "lab"
        assert n.data["patient_id"] == str(seed.patient.id)
        assert "analitica.pdf" not in n.data.values()

    def test_without_assigned_doctor_falls_back_to_last_consultation(self):
        seed = seed_clinic()
        other = build_user(seed.tenant.id, Role.DOCTOR, name="Dr. Otro", email="otro@x.test")
        seed.factory.store.users[other.id.value] = other
        seed.patient.primary_doctor_id = None
        _sign_a_record(seed, seed.factory.for_tenant(seed.tenant.id))  # seed.doctor, completed

        self._upload(seed, seed.actor(other))

        assert [n.type for n in _inbox(seed, seed.doctor)] == [DOCUMENT_UPLOADED]

    def test_patient_with_no_doctor_notifies_nobody(self):
        seed = seed_clinic()
        seed.patient.primary_doctor_id = None

        self._upload(seed, seed.actor(seed.nurse))

        assert seed.factory.store.notifications == {}

    def test_assigned_doctor_uploading_is_not_notified(self):
        seed = seed_clinic()
        self._upload(seed, seed.doctor_actor)
        assert _inbox(seed, seed.doctor) == []


class TestUserNotifications:
    def _second_admin(self, seed):
        admin2 = build_user(seed.tenant.id, Role.ADMIN, name="Admin Dos", email="a2@x.test")
        seed.factory.store.users[admin2.id.value] = admin2
        return admin2

    def test_new_user_notifies_the_other_admins(self):
        seed = seed_clinic()
        admin2 = self._second_admin(seed)
        uow = seed.factory.for_tenant(seed.tenant.id)

        user = InviteUser(uow, PlainPasswordHasher(), FixedClock()).execute(
            seed.actor(seed.admin),
            InviteUserCommand(
                name="Nuevo Admin", email="nuevo@x.test", role=Role.ADMIN, password="Rio-Lempa-482"
            ),
        )

        [n] = _inbox(seed, admin2)
        assert n.type == USER_CREATED
        assert n.data == {
            "user_id": str(user.id),
            "user_name": "Nuevo Admin",
            "role": "admin",
            "actor_name": seed.admin.name,
        }
        assert _inbox(seed, seed.admin) == []  # the actor
        assert _inbox(seed, user) == []  # the new admin is not told about themselves
        assert _inbox(seed, seed.doctor) == []  # not an admin

    def test_role_change_notifies_admins_with_both_roles(self):
        seed = seed_clinic()
        admin2 = self._second_admin(seed)
        uow = seed.factory.for_tenant(seed.tenant.id)

        UpdateUserRole(uow, FixedClock()).execute(
            seed.actor(seed.admin), seed.nurse.id, Role.RECEPTIONIST
        )

        [n] = _inbox(seed, admin2)
        assert n.type == USER_ROLE_CHANGED
        assert n.data["previous_role"] == "nurse"
        assert n.data["role"] == "receptionist"

    def test_profile_edit_notifies_only_when_the_role_changes(self):
        seed = seed_clinic()
        admin2 = self._second_admin(seed)
        uow = seed.factory.for_tenant(seed.tenant.id)
        update = UpdateUser(uow, FixedClock())

        update.execute(seed.actor(seed.admin), seed.nurse.id, phone="600000000")
        assert _inbox(seed, admin2) == []

        update.execute(seed.actor(seed.admin), seed.nurse.id, role=Role.DOCTOR)
        assert [n.type for n in _inbox(seed, admin2)] == [USER_ROLE_CHANGED]

    def test_suspended_admins_are_not_notified(self):
        seed = seed_clinic()
        admin2 = self._second_admin(seed)
        admin2.suspend()
        uow = seed.factory.for_tenant(seed.tenant.id)

        UpdateUserRole(uow, FixedClock()).execute(
            seed.actor(seed.admin), seed.nurse.id, Role.RECEPTIONIST
        )

        assert seed.factory.store.notifications == {}


def _put(
    seed, user, *, minutes_ago: int, read_at: datetime | None = None, type=APPOINTMENT_CREATED
) -> Notification:
    n = Notification(
        id=NotificationId.new(),
        tenant_id=seed.tenant.id,
        user_id=user.id,
        type=type,
        data={"appointment_code": f"A-{minutes_ago}"},
        read_at=read_at,
        created_at=FixedClock().now() - timedelta(minutes=minutes_ago),
    )
    seed.factory.store.notifications[n.id.value] = n
    return n


class TestInbox:
    def test_lists_newest_first_with_paging_and_unread_filter(self):
        seed = seed_clinic()
        old = _put(seed, seed.doctor, minutes_ago=30, read_at=FixedClock().now())
        mid = _put(seed, seed.doctor, minutes_ago=20)
        new = _put(seed, seed.doctor, minutes_ago=10)
        _put(seed, seed.nurse, minutes_ago=5)  # someone else's
        uow = seed.factory.for_tenant(seed.tenant.id)
        inbox = ListMyNotifications(uow)

        assert [n.id for n in inbox.execute(seed.doctor_actor)] == [new.id, mid.id, old.id]
        assert [n.id for n in inbox.execute(seed.doctor_actor, unread_only=True)] == [
            new.id,
            mid.id,
        ]
        page = inbox.execute(seed.doctor_actor, paging=Paging(offset=1, limit=1))
        assert [n.id for n in page] == [mid.id]
        assert CountMyUnreadNotifications(uow).execute(seed.doctor_actor) == 2

    def test_filters_by_category_combined_with_unread(self):
        seed = seed_clinic()
        appt = _put(seed, seed.doctor, minutes_ago=30)
        amended = _put(seed, seed.doctor, minutes_ago=20, type="record.amended")
        _put(seed, seed.doctor, minutes_ago=15, type="record.amended", read_at=FixedClock().now())
        doc = _put(seed, seed.doctor, minutes_ago=10, type="document.uploaded")
        inbox = ListMyNotifications(seed.factory.for_tenant(seed.tenant.id))

        assert [n.id for n in inbox.execute(seed.doctor_actor, category="appointment")] == [
            appt.id
        ]
        assert len(inbox.execute(seed.doctor_actor, category="record")) == 2
        assert [
            n.id for n in inbox.execute(seed.doctor_actor, unread_only=True, category="record")
        ] == [amended.id]
        assert [n.id for n in inbox.execute(seed.doctor_actor, category="document")] == [doc.id]
        assert inbox.execute(seed.doctor_actor, category="user") == []

    def test_mark_read(self):
        seed = seed_clinic()
        n = _put(seed, seed.doctor, minutes_ago=1)
        uow = seed.factory.for_tenant(seed.tenant.id)

        result = MarkNotificationRead(uow, FixedClock()).execute(seed.doctor_actor, n.id)

        assert result.read_at == FixedClock().now()
        assert CountMyUnreadNotifications(uow).execute(seed.doctor_actor) == 0

    def test_cannot_mark_someone_elses_notification(self):
        seed = seed_clinic()
        n = _put(seed, seed.nurse, minutes_ago=1)
        uow = seed.factory.for_tenant(seed.tenant.id)

        with pytest.raises(EntityNotFound):
            MarkNotificationRead(uow, FixedClock()).execute(seed.doctor_actor, n.id)
        assert not n.is_read

    def test_mark_all_read_only_touches_own_notifications(self):
        seed = seed_clinic()
        _put(seed, seed.doctor, minutes_ago=2)
        _put(seed, seed.doctor, minutes_ago=1)
        theirs = _put(seed, seed.nurse, minutes_ago=1)
        uow = seed.factory.for_tenant(seed.tenant.id)

        assert MarkAllNotificationsRead(uow, FixedClock()).execute(seed.doctor_actor) == 2
        assert CountMyUnreadNotifications(uow).execute(seed.doctor_actor) == 0
        assert not theirs.is_read

    def test_acknowledging_prunes_read_notifications_past_retention(self):
        seed = seed_clinic()
        now = FixedClock().now()
        stale = _put(seed, seed.doctor, minutes_ago=1, read_at=now - timedelta(days=91))
        recent = _put(seed, seed.doctor, minutes_ago=1, read_at=now - timedelta(days=89))
        unread = _put(seed, seed.doctor, minutes_ago=1)
        uow = seed.factory.for_tenant(seed.tenant.id)

        MarkAllNotificationsRead(uow, FixedClock()).execute(seed.doctor_actor)

        remaining = set(seed.factory.store.notifications)
        assert stale.id.value not in remaining
        assert {recent.id.value, unread.id.value} <= remaining

    def test_impersonation_reads_but_never_marks_as_read(self):
        seed = seed_clinic()
        n = _put(seed, seed.doctor, minutes_ago=1)
        uow = seed.factory.for_tenant(seed.tenant.id)
        support = replace(seed.doctor_actor, impersonated_by=PlatformAdminId.new())

        assert len(ListMyNotifications(uow).execute(support)) == 1
        MarkNotificationRead(uow, FixedClock()).execute(support, n.id)
        assert MarkAllNotificationsRead(uow, FixedClock()).execute(support) == 0
        assert not n.is_read
