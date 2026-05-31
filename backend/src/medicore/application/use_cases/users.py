"""User management use cases (admin)."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import ensure_can_manage_users
from medicore.application.ports.clock import Clock
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.user import User
from medicore.domain.enums import Role, UserStatus
from medicore.domain.repositories._support import Page, Paging, UserFilter
from medicore.domain.shared.identifiers import UserId


@dataclass(frozen=True, slots=True)
class InviteUserCommand:
    name: str
    email: str
    role: Role
    specialty: str | None = None


class ListUsers:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(
        self, actor: ActorContext, filter: UserFilter | None = None, paging: Paging | None = None
    ) -> Page[User]:
        ensure_can_manage_users(actor)
        return self._uow.users.list(filter, paging)


class InviteUser:
    """Create a pending user account (no password set until the invite is accepted)."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: InviteUserCommand) -> User:
        ensure_can_manage_users(actor)
        if self._uow.users.get_by_email(cmd.email) is not None:
            raise ValidationError(f"email already in use within this tenant: {cmd.email}")

        user = User(
            id=UserId.new(),
            tenant_id=actor.tenant_id,
            name=cmd.name,
            email=cmd.email,
            password_hash="",  # set when the invitation is accepted
            role=cmd.role,
            status=UserStatus.PENDING,
            specialty=cmd.specialty,
            joined_at=self._clock.now(),
        )
        with self._uow:
            self._uow.users.save(user)
            self._uow.audit.append(
                audit_entry(actor, self._clock.now(), "user.invited", "User", str(user.id))
            )
            self._uow.commit()
        return user


class UpdateUserRole:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, user_id: UserId, role: Role) -> User:
        ensure_can_manage_users(actor)
        user = self._require(user_id)
        with self._uow:
            user.change_role(role)
            self._uow.users.save(user)
            self._uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "user.role_changed", "User", str(user.id),
                    role=str(role),
                )
            )
            self._uow.commit()
        return user

    def _require(self, user_id: UserId) -> User:
        user = self._uow.users.get_by_id(user_id)
        if user is None:
            raise EntityNotFound("User", user_id)
        return user


class SuspendUser:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, user_id: UserId) -> User:
        ensure_can_manage_users(actor)
        user = self._uow.users.get_by_id(user_id)
        if user is None:
            raise EntityNotFound("User", user_id)
        with self._uow:
            user.suspend()
            self._uow.users.save(user)
            self._uow.audit.append(
                audit_entry(actor, self._clock.now(), "user.suspended", "User", str(user.id))
            )
            self._uow.commit()
        return user
