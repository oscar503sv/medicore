"""First-login onboarding: the "getting started" checklist for doctors and admins.

Every step is detected from real clinic data, so it ticks itself off as the user works;
nothing is tracked by hand. Only whether the welcome modal was shown and whether the
checklist was dismissed are stored, in the user's preferences. Other roles get no steps.
"""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound
from medicore.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from medicore.domain.entities.user import User
from medicore.domain.enums import AddonModule, Role
from medicore.domain.repositories._support import Paging


@dataclass(frozen=True, slots=True)
class OnboardingStep:
    key: str
    done: bool
    optional: bool = False


@dataclass(frozen=True, slots=True)
class OnboardingDTO:
    welcome_seen: bool
    dismissed: bool
    steps: tuple[OnboardingStep, ...]


def _doctor_steps(uow: UnitOfWork, user: User) -> list[OnboardingStep]:
    availability = uow.availability.get_by_doctor(user.id)
    profile = uow.doctor_profiles.get_by_user_id(user.id)
    return [
        OnboardingStep(
            "availability",
            availability is not None
            and any(d.enabled and d.blocks for d in availability.weekly),
        ),
        OnboardingStep("patient", uow.patients.list(paging=Paging(limit=1)).total > 0),
        OnboardingStep("appointment", uow.appointments.exists_for_doctor(user.id)),
        OnboardingStep("consultation", uow.medical_records.exists_by_author(user.id)),
        OnboardingStep(
            "profile", bool(user.phone and profile and profile.bio), optional=True
        ),
    ]


def _admin_steps(uow: UnitOfWork, user: User) -> list[OnboardingStep]:
    tenant = uow.tenants.get_by_id(user.tenant_id)
    primary = next((loc for loc in tenant.locations if loc.is_primary), None) if tenant else None
    steps = [
        OnboardingStep("clinic", bool(primary and primary.address)),
        OnboardingStep("insurers", bool(uow.insurers.list())),
        # The admin themself is always there: the team starts at the second user.
        OnboardingStep("team", uow.users.list(paging=Paging(limit=2)).total > 1),
    ]
    # The procedure catalog is part of the optional procedures module.
    if tenant and tenant.subscription.has_module(AddonModule.PROCEDURES):
        # Opening the catalog creates the clinic's default procedures.
        steps.append(OnboardingStep("catalog", bool(uow.procedures.list_types())))
    steps.append(OnboardingStep("roles", bool(uow.role_permissions.list()), optional=True))
    return steps


_STEPS = {Role.DOCTOR: _doctor_steps, Role.ADMIN: _admin_steps}


class GetOnboarding:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext) -> OnboardingDTO:
        with self._factory.for_tenant(actor.tenant_id) as uow:
            user = uow.users.get_by_id(actor.user_id)
            if user is None:
                raise EntityNotFound("User", actor.user_id)
            prefs = user.preferences
            build = _STEPS.get(user.role)
            # A dismissed checklist is never shown again: skip the lookups.
            steps = build(uow, user) if build and not prefs.onboarding_dismissed else []
            return OnboardingDTO(
                welcome_seen=prefs.welcome_seen,
                dismissed=prefs.onboarding_dismissed,
                steps=tuple(steps),
            )


class UpdateOnboarding:
    """Record that the welcome modal was shown and/or that the checklist was dismissed.
    Both flags only ever turn on."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(
        self, actor: ActorContext, *, welcome_seen: bool = False, dismissed: bool = False
    ) -> None:
        with self._factory.for_tenant(actor.tenant_id) as uow:
            user = uow.users.get_by_id(actor.user_id)
            if user is None:
                raise EntityNotFound("User", actor.user_id)
            if dismissed:
                user.dismiss_onboarding()
            elif welcome_seen:
                user.mark_welcome_seen()
            uow.users.save(user)
            uow.commit()
