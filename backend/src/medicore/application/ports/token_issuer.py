"""TokenIssuer port — issues/decodes session tokens (JWT in fase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SessionClaims:
    """The claims carried by a session token.

    Tenant sessions carry ``tenant_id`` + ``role`` with ``scope="tenant"``. Platform (superadmin)
    sessions carry ``scope="platform"`` and no tenant/role — the ``user_id`` is a platform admin id.
    """

    user_id: str
    tenant_id: str | None = None
    role: str = ""
    scope: str = "tenant"
    impersonator: str | None = None  # platform admin id when this is a support session
    session_id: str | None = None  # AuthSession id (the ``sid`` claim); required to act


class TokenIssuer(Protocol):
    def issue(self, claims: SessionClaims) -> str: ...

    def decode(self, token: str) -> SessionClaims: ...

    def ttl_minutes(self, impersonated: bool = False) -> int:
        """Lifetime of the tokens this issuer emits, so the matching AuthSession row
        can be given the same expiry."""
        ...
