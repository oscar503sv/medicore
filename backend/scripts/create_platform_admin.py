"""Create (or update the password of) a platform superadmin.

Usage:
    .venv/Scripts/python scripts/create_platform_admin.py <email> <name> <password>

Idempotent: if an admin with the email already exists, its name/password are updated.
"""

from __future__ import annotations

import sys

from medicore.domain.entities.platform_admin import PlatformAdmin
from medicore.domain.shared.identifiers import PlatformAdminId
from medicore.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from medicore.infrastructure.database.engine import get_session
from medicore.infrastructure.persistence.repositories.platform import SqlPlatformAdminRepository


def main(email: str, name: str, password: str) -> None:
    if len(password) < 8:
        raise SystemExit("password must be at least 8 characters")
    hasher = BcryptPasswordHasher()
    session = get_session()
    try:
        repo = SqlPlatformAdminRepository(session)
        existing = repo.get_by_email(email)
        if existing is not None:
            existing.name = name
            existing.change_password(hasher.hash(password))
            repo.save(existing)
            action = "updated"
        else:
            repo.save(
                PlatformAdmin(
                    id=PlatformAdminId.new(),
                    name=name,
                    email=email.strip().lower(),
                    password_hash=hasher.hash(password),
                )
            )
            action = "created"
        session.commit()
        print(f"platform admin {action}: {email}")
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: create_platform_admin.py <email> <name> <password>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
