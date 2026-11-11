"""Applies the domain password policy in the use cases that set a password.

Policy violations surface as ``ValidationError`` (HTTP 400) with the policy's own code
(``password.too_short``, ``password.common``…), like the rest of the input validation.
"""

from __future__ import annotations

from collections.abc import Iterable

from medicore.application.common.errors import ValidationError
from medicore.domain.services.password_policy import ensure_acceptable
from medicore.domain.shared.errors import InvalidValueObject


def ensure_password_policy(password: str, *, personal: Iterable[str | None] = ()) -> None:
    try:
        ensure_acceptable(password, personal=personal)
    except InvalidValueObject as exc:
        raise ValidationError(str(exc), code=exc.code, **exc.params) from exc
