"""Tests for the first-login "getting started" checklist."""

from __future__ import annotations

from medicore.application.use_cases.insurers import CreateInsurer, CreateInsurerCommand
from medicore.application.use_cases.onboarding import GetOnboarding, UpdateOnboarding
from medicore.application.use_cases.organization import UpdateLocation
from medicore.application.use_cases.procedures import GetProcedureCatalog
from medicore.domain.entities.availability import DoctorAvailability
from medicore.domain.shared.identifiers import AvailabilityId
from tests.application.test_records_and_permissions import _sign_a_record
from tests.support.builders import seed_clinic
from tests.support.fakes import FixedClock


def _steps(seed, user) -> dict[str, bool]:
    o = GetOnboarding(seed.factory).execute(seed.actor(user))
    return {s.key: s.done for s in o.steps}


class TestDoctorSteps:
    def test_steps_tick_off_from_real_data(self):
        seed = seed_clinic()  # the doctor already works Mon–Fri and the clinic has a patient
        steps = _steps(seed, seed.doctor)
        assert steps == {
            "availability": True,
            "patient": True,
            "appointment": False,
            "consultation": False,
            "profile": False,
        }

        _sign_a_record(seed, seed.factory.for_tenant(seed.tenant.id))

        steps = _steps(seed, seed.doctor)
        assert steps["appointment"] and steps["consultation"]

    def test_saved_schedule_without_working_days_is_not_configured(self):
        seed = seed_clinic()
        seed.factory.store.availability.clear()
        empty = DoctorAvailability(
            id=AvailabilityId.new(), tenant_id=seed.tenant.id, doctor_id=seed.doctor.id
        )
        seed.factory.store.availability[empty.id.value] = empty
        assert _steps(seed, seed.doctor)["availability"] is False

    def test_profile_needs_phone_and_bio(self):
        seed = seed_clinic()
        seed.doctor.phone = "7012-3456"
        assert _steps(seed, seed.doctor)["profile"] is False
        from medicore.application.use_cases.auth import UpdateMyProfile

        UpdateMyProfile(seed.factory, FixedClock()).execute(
            seed.actor(seed.doctor), bio="Ginecología y obstetricia"
        )
        o = GetOnboarding(seed.factory).execute(seed.actor(seed.doctor))
        profile = next(s for s in o.steps if s.key == "profile")
        assert profile.done and profile.optional


class TestAdminSteps:
    def test_steps_tick_off_from_real_data(self):
        seed = seed_clinic()
        steps = _steps(seed, seed.admin)
        # The seeded clinic already has more staff than the admin.
        assert steps == {
            "clinic": False,
            "insurers": False,
            "team": True,
            "catalog": False,
            "roles": False,
        }

        uow = seed.factory.for_tenant(seed.tenant.id)
        CreateInsurer(uow, FixedClock()).execute(
            seed.actor(seed.admin), CreateInsurerCommand(name="SISA", phone=None, address=None)
        )
        GetProcedureCatalog(uow, FixedClock()).execute(seed.actor(seed.admin))
        UpdateLocation(uow, FixedClock()).execute(
            seed.actor(seed.admin), seed.tenant.primary_location.id, address="Col. Escalón"
        )

        steps = _steps(seed, seed.admin)
        assert steps["clinic"] and steps["insurers"] and steps["catalog"]

    def test_team_is_pending_while_the_admin_is_alone(self):
        seed = seed_clinic()
        for uid in [u for u, user in seed.factory.store.users.items() if user != seed.admin]:
            del seed.factory.store.users[uid]
        assert _steps(seed, seed.admin)["team"] is False


class TestFlags:
    def test_other_roles_get_no_steps(self):
        seed = seed_clinic()
        assert GetOnboarding(seed.factory).execute(seed.actor(seed.nurse)).steps == ()
        assert GetOnboarding(seed.factory).execute(seed.actor(seed.receptionist)).steps == ()

    def test_welcome_then_dismiss(self):
        seed = seed_clinic()
        actor = seed.actor(seed.doctor)
        o = GetOnboarding(seed.factory).execute(actor)
        assert (o.welcome_seen, o.dismissed) == (False, False)

        UpdateOnboarding(seed.factory).execute(actor, welcome_seen=True)
        o = GetOnboarding(seed.factory).execute(actor)
        assert (o.welcome_seen, o.dismissed) == (True, False)
        assert o.steps

        UpdateOnboarding(seed.factory).execute(actor, dismissed=True)
        o = GetOnboarding(seed.factory).execute(actor)
        assert (o.welcome_seen, o.dismissed) == (True, True)
        assert o.steps == ()

    def test_flags_never_turn_off(self):
        seed = seed_clinic()
        actor = seed.actor(seed.admin)
        UpdateOnboarding(seed.factory).execute(actor, dismissed=True)
        UpdateOnboarding(seed.factory).execute(actor)
        assert GetOnboarding(seed.factory).execute(actor).dismissed
