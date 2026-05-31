"""Authentication and session use cases."""

from __future__ import annotations

from dataclasses import dataclass

from medicore.application.common.context import ActorContext
from medicore.application.common.errors import AuthenticationFailed, EntityNotFound
from medicore.application.ports.clock import Clock
from medicore.application.ports.password_hasher import PasswordHasher
from medicore.application.ports.token_issuer import SessionClaims, TokenIssuer
from medicore.application.ports.unit_of_work import UnitOfWorkFactory
from medicore.domain.entities.audit_log import AuditLog
from medicore.domain.enums import LangPref, Role, ThemePref, UserStatus
from medicore.domain.shared.errors import InvalidValueObject
from medicore.domain.shared.identifiers import AuditLogId, TenantId, UserId
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
    role: Role
    name: str


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

        tenant = self._factory.global_tenants().get_by_slug(slug)
        if tenant is None:
            raise AuthenticationFailed("invalid organization")

        uow = self._factory.for_tenant(tenant.id)
        user = uow.users.get_by_email(cmd.email)
        if user is None or not self._hasher.verify(cmd.password, user.password_hash):
            raise AuthenticationFailed("invalid credentials")
        if user.status != UserStatus.ACTIVE:
            raise AuthenticationFailed("account is not active")

        with uow:
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
            role=user.role,
            name=user.name,
        )


class SwitchTheme:
    """Persist the actor's theme preference."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext, theme: ThemePref) -> None:
        uow = self._factory.for_tenant(actor.tenant_id)
        user = uow.users.get_by_id(actor.user_id)
        if user is None:
            raise EntityNotFound("User", actor.user_id)
        with uow:
            user.set_theme(theme)
            uow.users.save(user)
            uow.commit()


class SwitchLocale:
    """Persist the actor's language preference."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._factory = uow_factory

    def execute(self, actor: ActorContext, language: LangPref) -> None:
        uow = self._factory.for_tenant(actor.tenant_id)
        user = uow.users.get_by_id(actor.user_id)
        if user is None:
            raise EntityNotFound("User", actor.user_id)
        with uow:
            user.set_language(language)
            uow.users.save(user)
            uow.commit()
