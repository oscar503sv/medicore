"""UserRepository and DoctorProfileRepository ports."""

from __future__ import annotations

from typing import Protocol

from medicore.domain.entities.user import DoctorProfile, User
from medicore.domain.repositories._support import Page, Paging, UserFilter
from medicore.domain.shared.identifiers import UserId


class UserRepository(Protocol):
    def get_by_id(self, user_id: UserId) -> User | None: ...

    def get_by_email(self, email: str) -> User | None:
        """Within the current tenant scope; email is unique per tenant."""
        ...

    def list(
        self, filter: UserFilter | None = None, paging: Paging | None = None
    ) -> Page[User]: ...

    def save(self, user: User) -> None: ...


class DoctorProfileRepository(Protocol):
    def get_by_user_id(self, user_id: UserId) -> DoctorProfile | None: ...

    def save(self, profile: DoctorProfile) -> None: ...
