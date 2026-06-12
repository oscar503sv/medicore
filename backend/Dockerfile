# Medicore backend — production image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package + runtime deps (psycopg[binary] bundles libpq — no system libs needed).
# README.md is copied because pyproject.toml references it as the project readme.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Migrations (run `alembic upgrade head` as a separate step before/at deploy).
COPY alembic.ini ./
COPY migrations ./migrations

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# Single worker by default; scale with --workers N or run behind a process manager.
# --no-proxy-headers: the app resolves X-Forwarded-For itself against TRUSTED_PROXIES;
# uvicorn's own (default-on) proxy handling would rewrite request.client first and
# bypass that single source of truth.
CMD ["uvicorn", "medicore.presentation.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
