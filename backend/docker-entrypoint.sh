#!/bin/sh
# Apply pending migrations, then hand off to the container command (uvicorn by default).
# Migrations run as the schema owner (MIGRATIONS_DATABASE_URL); that URL is removed before the
# command starts, so the API process only ever holds the DML-only DATABASE_URL.
# Set SKIP_MIGRATIONS=1 to start without migrating (e.g. one-off script containers).
set -e

if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
fi

exec env -u MIGRATIONS_DATABASE_URL "$@"
