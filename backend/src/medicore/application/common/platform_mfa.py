"""Rules of the superadmin second factor (TOTP + recovery codes)."""

from __future__ import annotations

import hashlib
import secrets

from medicore.domain.entities.platform_admin import PlatformAdmin

RECOVERY_CODE_COUNT = 10
RECOVERY_LOW_WATERMARK = 3
_RECOVERY_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_RECOVERY_HALF = 5
_TOTP_DIGITS = 6


def mfa_required_for(admin: PlatformAdmin, *, enforced: bool = False) -> bool:
    """Whether signing in as ``admin`` needs the second step.

    MFA is optional today: only admins who turned it on. ``enforced`` is the extension point
    for a future PLATFORM_MFA_REQUIRED setting (every superadmin must have it, with a forced
    enrollment at first sign-in); the setting does not exist yet, so callers leave it False.
    """
    return admin.mfa_enabled or enforced


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    return [
        "-".join(
            "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_HALF))
            for _ in range(2)
        )
        for _ in range(count)
    ]


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def hash_recovery_code(code: str) -> str:
    # A fast hash is fine here: the codes carry 50 bits of entropy and are single-use.
    return hashlib.sha256(normalize_recovery_code(code).encode()).hexdigest()


def looks_like_totp(code: str) -> bool:
    candidate = code.replace(" ", "")
    return len(candidate) == _TOTP_DIGITS and candidate.isascii() and candidate.isdigit()
