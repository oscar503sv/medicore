"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from medicore.presentation.error_handlers import register_error_handlers
from medicore.presentation.routers import (
    appointments,
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
    app = FastAPI(
        title="Medicore API",
        description="Multi-tenant clinical management system",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_credentials=True,
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
    app.include_router(platform.router, prefix=API_PREFIX)

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return app
