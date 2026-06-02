"""User management use cases (admin)."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import EntityNotFound, ValidationError
from medicore.application.common.permissions import ensure_can_manage_users
from medicore.application.ports.clock import Clock
from medicore.application.ports.password_hasher import PasswordHasher
from medicore.application.ports.unit_of_work import UnitOfWork
from medicore.domain.entities.user import User
from medicore.domain.enums import Role, Sex, UserStatus
from medicore.domain.repositories._support import Page, Paging, UserFilter
from medicore.domain.shared.identifiers import UserId


@dataclass(frozen=True, slots=True)
class InviteUserCommand:
    name: str
    email: str
    role: Role
    password: str
    sex: Sex | None = None
    phone: str | None = None
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
    """Create an active user account with a temporary password.

    The new user must change their password on first login (``must_change_password``).
    """

    def __init__(self, uow: UnitOfWork, hasher: PasswordHasher, clock: Clock) -> None:
        self._uow = uow
        self._hasher = hasher
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: InviteUserCommand) -> User:
        ensure_can_manage_users(actor)
        if self._uow.users.get_by_email(cmd.email) is not None:
            raise ValidationError(f"email already in use within this tenant: {cmd.email}")
        if not cmd.password or len(cmd.password) < 8:
            raise ValidationError("temporary password must be at least 8 characters")

        user = User(
            id=UserId.new(),
            tenant_id=actor.tenant_id,
            name=cmd.name,
            email=cmd.email,
            password_hash=self._hasher.hash(cmd.password),
            role=cmd.role,
            status=UserStatus.ACTIVE,
            sex=cmd.sex,
            specialty=cmd.specialty,
            phone=cmd.phone,
            must_change_password=True,
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


class UpdateUser:
    """Edit a user's profile fields (and role). Email is immutable here."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, user_id: UserId, **changes: object) -> User:
        ensure_can_manage_users(actor)
        user = self._uow.users.get_by_id(user_id)
        if user is None:
            raise EntityNotFound("User", user_id)
        allowed = {"name", "role", "sex", "phone", "specialty"}
        with self._uow:
            for key, value in changes.items():
                if key in allowed:
                    setattr(user, key, value)
            self._uow.users.save(user)
            self._uow.audit.append(
                audit_entry(actor, self._clock.now(), "user.updated", "User", str(user.id))
            )
            self._uow.commit()
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


class ReactivateUser:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, actor: ActorContext, user_id: UserId) -> User:
        ensure_can_manage_users(actor)
        user = self._uow.users.get_by_id(user_id)
        if user is None:
            raise EntityNotFound("User", user_id)
        with self._uow:
            user.activate()
            self._uow.users.save(user)
            self._uow.audit.append(
                audit_entry(actor, self._clock.now(), "user.reactivated", "User", str(user.id))
            )
            self._uow.commit()
        return user


@dataclass(frozen=True, slots=True)
class ResetUserPasswordCommand:
    user_id: UserId
    password: str


class ResetUserPassword:
    """Admin sets a new temporary password; the user must change it on next login."""

    def __init__(self, uow: UnitOfWork, hasher: PasswordHasher, clock: Clock) -> None:
        self._uow = uow
        self._hasher = hasher
        self._clock = clock

    def execute(self, actor: ActorContext, cmd: ResetUserPasswordCommand) -> User:
        ensure_can_manage_users(actor)
        if not cmd.password or len(cmd.password) < 8:
            raise ValidationError("temporary password must be at least 8 characters")
        user = self._uow.users.get_by_id(cmd.user_id)
        if user is None:
            raise EntityNotFound("User", cmd.user_id)
        with self._uow:
            user.set_temporary_password(self._hasher.hash(cmd.password))
            self._uow.users.save(user)
            self._uow.audit.append(
                audit_entry(actor, self._clock.now(), "user.password_reset", "User", str(user.id))
            )
            self._uow.commit()
        return user
