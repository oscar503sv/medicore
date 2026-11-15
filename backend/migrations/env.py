"""Alembic environment: wires ORM metadata + DB URL from .env for autogenerate."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from medicore.infrastructure.config import get_settings
from medicore.infrastructure.database.base import Base
from medicore.infrastructure.database.role_guard import assert_migration_role_is_not_superuser

# Import all ORM models so autogenerate sees them.
import medicore.infrastructure.persistence.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations run as the schema owner (MIGRATIONS_DATABASE_URL); never hardcoded in alembic.ini.
# configparser treats "%" as interpolation: escape it so URL-encoded passwords survive.
config.set_main_option("sqlalchemy.url", get_settings().owner_database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        if get_settings().is_production:
            assert_migration_role_is_not_superuser(connection)
            connection.rollback()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
