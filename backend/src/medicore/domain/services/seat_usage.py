"""How active users count against a subscription's seat quotas."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.domain.enums import Role


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
