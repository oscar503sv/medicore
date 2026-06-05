"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from medicore.infrastructure.config import get_settings
from medicore.presentation.error_handlers import register_error_handlers
from medicore.presentation.routers import (
    appointments,
    audit,
    auth,
    availability,
    consultations,
    diagnoses,
    insurers,
    organization,
    patients,
    platform,
    records,
    users,
)

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    docs_enabled = settings.enable_docs

    app = FastAPI(
        title="Medicore API",
        description="Multi-tenant clinical management system",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs" if docs_enabled else None,
        redoc_url=f"{API_PREFIX}/redoc" if docs_enabled else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs_enabled else None,
    )

    # CORS origins from config (default "*" for dev). With explicit origins we may allow
    # credentials; with "*" they must be disabled per the CORS spec (the frontend uses Bearer
    # tokens in headers, not cookies, so this never affects auth).
    origins = settings.cors_origins_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(patients.router, prefix=API_PREFIX)
    app.include_router(insurers.router, prefix=API_PREFIX)
    app.include_router(appointments.router, prefix=API_PREFIX)
    app.include_router(consultations.router, prefix=API_PREFIX)
    app.include_router(diagnoses.router, prefix=API_PREFIX)
    app.include_router(records.router, prefix=API_PREFIX)
    app.include_router(availability.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(organization.router, prefix=API_PREFIX)
    app.include_router(audit.router, prefix=API_PREFIX)
    app.include_router(platform.router, prefix=API_PREFIX)

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return app
