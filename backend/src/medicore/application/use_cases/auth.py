"""Authentication and session use cases."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.audit import audit_entry, subject
from medicore.application.common.context import ActorContext
from medicore.application.common.errors import AuthenticationFailed, EntityNotFound
from medicore.application.common.permissions import effective_permissions
from medicore.application.ports.clock import Clock
from medicore.application.ports.password_hasher import PasswordHasher
from medicore.application.ports.token_issuer import SessionClaims, TokenIssuer
from medicore.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.entities.user import DoctorProfile
from medicore.domain.enums import LangPref, Role, Sex, ThemePref, UserStatus
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import AuditLogId, DoctorProfileId, TenantId, UserId
from medicore.domain.value_objects.slug import Slug


@dataclass(frozen=True, slots=True)
class AuthenticateUserCommand:
    slug: str
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class SessionDTO:
    token: str
    user_id: UserId
    tenant_id: TenantId
    tenant_name: str
    timezone: str
    role: Role
    name: str
    sex: Sex | None
    must_change_password: bool
    permissions: tuple[str, ...] = ()


class AuthenticateUser:
    """Authenticate a user against an organization (tenant) identified by its slug."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        tokens: TokenIssuer,
        clock: Clock,
    ) -> None:
        self._factory = uow_factory
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock

    def execute(self, cmd: AuthenticateUserCommand) -> SessionDTO:
        try:
            slug = Slug(cmd.slug.strip().lower())
        except InvalidValueObject as exc:
            raise AuthenticationFailed("invalid organization") from exc

        with self._factory.global_tenants() as tenants:
            tenant = tenants.get_by_slug(slug)
        if tenant is None:
            raise AuthenticationFailed("invalid organization")
        if not tenant.is_active:
            raise AuthenticationFailed("this organization is not active")

        with self._factory.for_tenant(tenant.id) as uow:
            user = uow.users.get_by_email(cmd.email)
            if user is None or not self._hasher.verify(cmd.password, user.password_hash):
                raise AuthenticationFailed("invalid credentials")
            if user.status != UserStatus.ACTIVE:
                raise AuthenticationFailed("account is not active")
            override = uow.role_permissions.get_by_role(user.role)
            user.last_seen_at = self._clock.now()
            uow.users.save(user)
            uow.audit.append(
                AuditLog(
                    id=AuditLogId.new(),
                    tenant_id=tenant.id,
                    actor_id=user.id,
                    action="auth.login",
                    entity_type="User",
                    entity_id=str(user.id),
                    timestamp=self._clock.now(),
                )
            )
            uow.commit()

        token = self._tokens.issue(
            SessionClaims(user_id=str(user.id), tenant_id=str(tenant.id), role=str(user.role))
        )
        return SessionDTO(
            token=token,
            user_id=user.id,
            tenant_id=tenant.id,
            tenant_name=tenant.legal_name,
            timezone=tenant.timezone,
            role=user.role,
            name=user.name,
            sex=user.sex,
            must_change_password=user.must_change_password,
            permissions=tuple(
                sorted(effective_permissions(user.role, override.permissions if override else None))
            ),
        )


class SwitchTheme:
    """Persist the actor's theme preference."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext, theme: ThemePref) -> None:
        with self._factory.for_tenant(actor.tenant_id) as uow:
            user = uow.users.get_by_id(actor.user_id)
            if user is None:
                raise EntityNotFound("User", actor.user_id)
            user.set_theme(theme)
            uow.users.save(user)
            uow.commit()


class SwitchLocale:
    """Persist the actor's language preference."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext, language: LangPref) -> None:
        with self._factory.for_tenant(actor.tenant_id) as uow:
            user = uow.users.get_by_id(actor.user_id)
            if user is None:
                raise EntityNotFound("User", actor.user_id)
            user.set_language(language)
            uow.users.save(user)
            uow.commit()


class ChangePassword:
    """Change the actor's own password, verifying the current one first.

    Used both for the forced change after a temporary-password invite and for
    routine password changes. Clears the ``must_change_password`` flag on success.
    """

    def __init__(self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher) -> None:
        self._factory = uow_factory
        self._hasher = hasher

    def execute(self, actor: ActorContext, current_password: str, new_password: str) -> None:
        if not new_password or len(new_password) < 8:
            raise AuthenticationFailed("new password must be at least 8 characters")
        with self._factory.for_tenant(actor.tenant_id) as uow:
            user = uow.users.get_by_id(actor.user_id)
            if user is None:
                raise EntityNotFound("User", actor.user_id)
            if not self._hasher.verify(current_password, user.password_hash):
                raise AuthenticationFailed("current password is incorrect")
            user.change_password(self._hasher.hash(new_password))
            uow.users.save(user)
            uow.commit()


@dataclass(frozen=True, slots=True)
class MyProfileDTO:
    name: str
    email: str
    role: Role
    sex: Sex | None
    specialty: str | None
    phone: str | None
    bio: str | None
    permissions: tuple[str, ...] = ()


def _build_profile(uow: UnitOfWork, user_id: UserId) -> MyProfileDTO:
    """Assemble the actor's profile from the User and (for doctors) their DoctorProfile."""
    user = uow.users.get_by_id(user_id)
    if user is None:
        raise EntityNotFound("User", user_id)
    bio = None
    if user.role == Role.DOCTOR:
        profile = uow.doctor_profiles.get_by_user_id(user_id)
        bio = profile.bio if profile else None
    override = uow.role_permissions.get_by_role(user.role)
    return MyProfileDTO(
        name=user.name,
        email=user.email,
        role=user.role,
        sex=user.sex,
        specialty=user.specialty,
        phone=user.phone,
        bio=bio,
        permissions=tuple(
            sorted(effective_permissions(user.role, override.permissions if override else None))
        ),
    )


class GetMyProfile:
    """Read the authenticated actor's own profile (no admin permission required)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext) -> MyProfileDTO:
        uow = self._factory.for_tenant(actor.tenant_id)
        with uow:
            return _build_profile(uow, actor.user_id)


class UpdateMyProfile:
    """Update the actor's own editable profile fields.

    Only ``name`` and ``phone`` are writable on the User; ``email``, ``role``, ``sex`` and
    ``specialty`` are immutable here. ``bio`` is persisted on the doctor's DoctorProfile
    (created on demand) and ignored for non-doctor users.
    """

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._factory = uow_factory
        self._clock = clock

    def execute(
        self,
        actor: ActorContext,
        *,
        name: str | None = None,
        phone: str | None = None,
        bio: str | None = None,
    ) -> MyProfileDTO:
        with self._factory.for_tenant(actor.tenant_id) as uow:
            user = uow.users.get_by_id(actor.user_id)
            if user is None:
                raise EntityNotFound("User", actor.user_id)
            if name is not None:
                user.name = name
            if phone is not None:
                user.phone = phone
            uow.users.save(user)
            if bio is not None and user.role == Role.DOCTOR:
                profile = uow.doctor_profiles.get_by_user_id(actor.user_id)
                if profile is None:
                    profile = DoctorProfile(
                        id=DoctorProfileId.new(),
                        user_id=actor.user_id,
                        tenant_id=actor.tenant_id,
                    )
                profile.bio = bio
                uow.doctor_profiles.save(profile)
            uow.audit.append(
                audit_entry(
                    actor, self._clock.now(), "user.profile_updated", "User", str(user.id),
                    subject=subject(user.name),
                )
            )
            uow.commit()
            return _build_profile(uow, actor.user_id)
