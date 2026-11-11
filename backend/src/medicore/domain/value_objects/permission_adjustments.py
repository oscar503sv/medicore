"""PermissionAdjustments value object (embedded in User): one person's exceptions to
their role's permissions — a few extra grants, a few revocations.

Held as permission strings: the catalog itself lives in the application layer. Whether the
adjustments apply at all depends on the clinic's plan (per-user permissions feature).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from medicore.domain.shared.errors import InvalidValueObject


@dataclass(frozen=True, slots=True)
class PermissionAdjustments:
    granted: frozenset[str] = frozenset()
    revoked: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        both = self.granted & self.revoked
        if both:
            raise InvalidValueObject(
                "a permission can't be both granted and revoked: " + ", ".join(sorted(both)),
                code="user_permissions.conflict",
                permissions=",".join(sorted(both)),
            )

    @classmethod
    def between(cls, base: Iterable[str], wanted: Iterable[str]) -> PermissionAdjustments:
        """The adjustments that turn ``base`` (the role's set) into ``wanted``."""
        base_set, wanted_set = frozenset(base), frozenset(wanted)
        return cls(granted=wanted_set - base_set, revoked=base_set - wanted_set)

    @property
    def is_empty(self) -> bool:
        return not self.granted and not self.revoked

    def apply(self, base: Iterable[str]) -> frozenset[str]:
        return (frozenset(base) | self.granted) - self.revoked
