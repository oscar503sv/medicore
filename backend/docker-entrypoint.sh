#!/bin/sh
# Apply pending migrations, then hand off to the container command (uvicorn by default).
# Set SKIP_MIGRATIONS=1 to start without migrating (e.g. one-off script containers).
set -e

if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
fi

exec "$@"
