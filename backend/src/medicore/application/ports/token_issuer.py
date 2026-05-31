"""TokenIssuer port — issues/decodes session tokens (JWT in fase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SessionClaims:
    """The claims carried by a session token: ``userId``, ``tenantId``, ``role``."""

    user_id: str
    tenant_id: str
    role: str


class TokenIssuer(Protocol):
    def issue(self, claims: SessionClaims) -> str: ...

    def decode(self, token: str) -> SessionClaims: ...
