"""Rules for platform-support actions on a clinic's accounts."""

from __future__ import annotations

from medicore.application.common.errors import ValidationError

SUPPORT_REASON_MIN = 5
SUPPORT_REASON_MAX = 500


def require_support_reason(reason: str | None) -> str:
    """The reason a superadmin gives for entering a clinic or resetting a password; it ends
    up in the clinic's audit trail, so it cannot be blank."""
    text = (reason or "").strip()
    if len(text) < SUPPORT_REASON_MIN:
        raise ValidationError(
            "a support reason is required", code="support.reason_required", min=SUPPORT_REASON_MIN
        )
    if len(text) > SUPPORT_REASON_MAX:
        raise ValidationError(
            "support reason too long", code="support.reason_too_long", max=SUPPORT_REASON_MAX
        )
    return text
