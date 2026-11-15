"""Startup checks that the database roles are split as intended (see scripts/db_roles.sql).

The API role must only hold DML: if it could alter schema, lift the append-only triggers or
bypass row security, signed clinical data would be one SQL injection away from rewriting.
"""

from __future__ import annotations

from sqlalchemy import Connection, text

_ROLE_FLAGS = text(
    "SELECT current_user, rolsuper, rolcreaterole, rolbypassrls "
    "FROM pg_roles WHERE rolname = current_user"
)
# Relations and routines of `public` owned by the connected role, extensions excluded.
_OWNED_OBJECTS = text(
    "SELECT count(*) FROM ("
    " SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
    "  WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','S','f')"
    "  AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
    "  AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass"
    "                  AND d.objid = c.oid AND d.deptype IN ('e','a','i'))"
    " UNION ALL"
    " SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
    "  WHERE n.nspname = 'public'"
    "  AND p.proowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
    "  AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass"
    "                  AND d.objid = p.oid AND d.deptype = 'e')"
    ") owned"
)


def assert_app_role_is_unprivileged(conn: Connection) -> None:
    """Refuse to serve with a role that is a superuser, creates roles, bypasses RLS or owns
    schema objects."""
    name, is_super, can_create_role, bypasses_rls = conn.execute(_ROLE_FLAGS).one()
    problems = [label for label, flag in (
        ("is a superuser", is_super),
        ("has CREATEROLE", can_create_role),
        ("has BYPASSRLS", bypasses_rls),
    ) if flag]
    owned = conn.execute(_OWNED_OBJECTS).scalar_one()
    if owned:
        problems.append(f"owns {owned} schema object(s)")
    if problems:
        raise RuntimeError(
            f"DATABASE_URL role {name!r} is too privileged ({', '.join(problems)}): the API "
            "must connect as a DML-only role. Run scripts/db_roles.sql and point DATABASE_URL "
            "at medicore_app."
        )


def assert_migration_role_is_not_superuser(conn: Connection) -> None:
    name, is_super, *_ = conn.execute(_ROLE_FLAGS).one()
    if is_super:
        raise RuntimeError(
            f"MIGRATIONS_DATABASE_URL role {name!r} is a superuser: migrate as the schema "
            "owner (medicore_owner) so the objects it creates belong to it."
        )
