"""Applies the domain access policy where a clinic session is opened or used: refusals
surface as AuthenticationFailed (HTTP 401), which makes the client drop its session."""

from __future__ import annotations

from medicore.application.common.errors import AuthenticationFailed
from medicore.domain.entities.tenant import Tenant
from medicore.domain.entities.user import User
from medicore.domain.services.access_policy import AccessRefused, ensure_may_access


def ensure_may_sign_in(tenant: Tenant, user: User, *, support: bool = False) -> None:
    try:
        ensure_may_access(tenant, user, support=support)
    except AccessRefused as exc:
        raise AuthenticationFailed(str(exc), code=exc.code, **exc.params) from exc
