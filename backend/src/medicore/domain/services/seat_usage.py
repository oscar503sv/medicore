"""How active users and sites count against a subscription's quotas, and the rule that
keeps a clinic within them."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.domain.enums import Role
from medicore.domain.shared.errors import QuotaExceeded
from medicore.domain.value_objects.plan_limits import PlanLimits


@dataclass(frozen=True, slots=True)
class SeatUsage:
    doctors: int
    support_users: int


def seat_usage(active_by_role: dict[Role, int]) -> SeatUsage:
    """Doctors count as doctors; nursing, reception and admins as support staff, except the
    clinic's first admin account, which never takes a seat."""
    admins = active_by_role.get(Role.ADMIN, 0)
    return SeatUsage(
        doctors=active_by_role.get(Role.DOCTOR, 0),
        support_users=(
            active_by_role.get(Role.NURSE, 0)
            + active_by_role.get(Role.RECEPTIONIST, 0)
            + max(admins - 1, 0)
        ),
    )


def check_quota(code: str, limit: int | None, before: int, after: int) -> None:
    """Reject a change that takes usage above the limit. A clinic already above it (say,
    after moving to a smaller plan) keeps what it has: only growing is refused."""
    if limit is not None and after > limit and after > before:
        raise QuotaExceeded(f"quota reached: {code} ({limit})", code=code, limit=limit)


QUOTA_DOCTORS = "plan.quota_doctors"
QUOTA_SUPPORT_USERS = "plan.quota_support_users"
QUOTA_LOCATIONS = "plan.quota_locations"


def ensure_seats(limits: PlanLimits, before: SeatUsage, after: SeatUsage) -> None:
    check_quota(QUOTA_DOCTORS, limits.doctors, before.doctors, after.doctors)
    check_quota(
        QUOTA_SUPPORT_USERS, limits.support_users, before.support_users, after.support_users
    )
