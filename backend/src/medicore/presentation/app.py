"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from medicore.application.common.request_stats import RequestRecorder
from medicore.application.use_cases.monitoring import CheckReadiness
from medicore.infrastructure.config import get_settings
from medicore.presentation.dependencies import get_uow_factory
from medicore.presentation.error_handlers import register_error_handlers
from medicore.presentation.request_metrics import RequestMetricsMiddleware
from medicore.presentation.routers import (
    analytics,
    applications,
    appointments,
    audit,
    auth,
    availability,
    certificates,
    consultations,
    dashboard,
    diagnoses,
    fees,
    insurers,
    notifications,
    organization,
    patients,
    platform,
    prescriptions,
    printing,
    procedures,
    records,
    role_permissions,
    subscriptions,
    users,
    vaccinations,
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

    # Per-route request metrics for the console's Monitoring page (added last: outermost,
    # so the timing covers CORS and the error handlers too).
    app.state.request_recorder = RequestRecorder()
    app.add_middleware(RequestMetricsMiddleware, recorder=app.state.request_recorder)

    hsts = settings.is_production

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if hsts:
            # Only meaningful behind TLS, so production-only.
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
        return response

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(patients.router, prefix=API_PREFIX)
    app.include_router(insurers.router, prefix=API_PREFIX)
    app.include_router(appointments.router, prefix=API_PREFIX)
    app.include_router(analytics.router, prefix=API_PREFIX)
    app.include_router(consultations.router, prefix=API_PREFIX)
    app.include_router(diagnoses.router, prefix=API_PREFIX)
    app.include_router(prescriptions.router, prefix=API_PREFIX)
    app.include_router(records.router, prefix=API_PREFIX)
    app.include_router(certificates.router, prefix=API_PREFIX)
    app.include_router(printing.router, prefix=API_PREFIX)
    app.include_router(availability.router, prefix=API_PREFIX)
    app.include_router(fees.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(notifications.router, prefix=API_PREFIX)
    app.include_router(dashboard.router, prefix=API_PREFIX)
    app.include_router(organization.router, prefix=API_PREFIX)
    app.include_router(audit.router, prefix=API_PREFIX)
    app.include_router(role_permissions.router, prefix=API_PREFIX)
    app.include_router(vaccinations.router, prefix=API_PREFIX)
    app.include_router(applications.router, prefix=API_PREFIX)
    app.include_router(procedures.router, prefix=API_PREFIX)
    app.include_router(platform.router, prefix=API_PREFIX)
    app.include_router(subscriptions.router, prefix=API_PREFIX)

    @app.get("/health", tags=["health"])
    def health():
        """Liveness: the process answers (no dependencies checked)."""
        return {"status": "ok"}

    # Also under the API prefix: the frontend's nginx only forwards /api/, so this is the
    # URL an external uptime monitor reaches (https://<domain>/api/v1/health/ready).
    @app.get("/health/ready", tags=["health"])
    @app.get(f"{API_PREFIX}/health/ready", tags=["health"], include_in_schema=False)
    def ready(request: Request):
        """Readiness: the API can serve requests, i.e. the database answers. For uptime
        monitors; 503 when the database is unreachable."""
        try:
            factory = request.app.dependency_overrides.get(get_uow_factory, get_uow_factory)()
            CheckReadiness(factory).execute()
        except Exception:
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "database": "down"}
            )
        return {"status": "ok", "database": "ok"}

    return app
