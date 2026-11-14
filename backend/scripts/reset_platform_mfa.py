"""Turn off the second factor of a superadmin who lost both the app and the recovery codes.

Usage:
    .venv/bin/python scripts/reset_platform_mfa.py <email>

Disables MFA, deletes the recovery codes, revokes every live session of the admin and records
``auth.platform_mfa_reset`` in the platform audit trail. The admin can enroll again afterwards.
"""

from __future__ import annotations

import sys

from medicore.application.common.errors import EntityNotFound
from medicore.application.use_cases.platform_mfa import ResetPlatformAdminMfa
from medicore.infrastructure.auth.system_clock import SystemClock
from medicore.infrastructure.database.engine import get_session_factory
from medicore.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory


def main(email: str) -> None:
    factory = SqlAlchemyUnitOfWorkFactory(get_session_factory())
    try:
        ResetPlatformAdminMfa(factory, SystemClock()).execute(email)
    except EntityNotFound as exc:
        raise SystemExit(f"no platform admin with email {email}") from exc
    print(f"MFA reset for {email} (recovery codes deleted, sessions revoked)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: reset_platform_mfa.py <email>")
    main(sys.argv[1])
