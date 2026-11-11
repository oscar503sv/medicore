"""Request metrics middleware: time every API request and count it per route template.

A plain ASGI middleware (no request/response wrapping): it notes the status from the
``http.response.start`` message, the duration, and the matched route template, which the
router leaves in the scope. Counts accumulate in the app's ``RequestRecorder``; once the
flush interval has passed, the request that finishes hands the batch to the database —
after its response has been sent, in a worker thread, so no client waits for it.

Only ``/api/v1`` traffic is measured (health probes, docs and static paths are not), and
CORS preflights are skipped.
"""

from __future__ import annotations

import logging
import time

from anyio import to_thread
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from medicore.application.common.request_stats import UNMATCHED_ROUTE, RequestRecorder
from medicore.application.use_cases.performance import FlushRequestStats, hour_of
from medicore.presentation.dependencies import get_clock, get_uow_factory

logger = logging.getLogger("medicore")

MEASURED_PREFIX = "/api/v1/"
SKIPPED_PATHS = frozenset({"/api/v1/health/ready"})


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp, recorder: RequestRecorder) -> None:
        self.app = app
        self.recorder = recorder

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope.get("method") == "OPTIONS"
            or not path.startswith(MEASURED_PREFIX)
            or path in SKIPPED_PATHS
        ):
            await self.app(scope, receive, send)
            return

        status = 500  # an exception that escapes everything still answers 500
        started = time.perf_counter()

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            ms = (time.perf_counter() - started) * 1000
            route = getattr(scope.get("route"), "path", None) or UNMATCHED_ROUTE
            self.recorder.record(hour_of(_clock(scope).now()), scope["method"], route, status, ms)
        if self.recorder.due():
            await to_thread.run_sync(_flush, scope, self.recorder)


def _overrides(scope: Scope) -> dict:
    return getattr(scope.get("app"), "dependency_overrides", None) or {}


def _clock(scope: Scope):
    """The app's clock (tests swap it through ``dependency_overrides``)."""
    return _overrides(scope).get(get_clock, get_clock)()


def _flush(scope: Scope, recorder: RequestRecorder) -> None:
    """Hand the recorder's batch to the store. Never raises: metrics must not break requests
    (a batch lost to a database hiccup is acceptable)."""
    rows = recorder.drain()
    try:
        factory = _overrides(scope).get(get_uow_factory, get_uow_factory)()
        FlushRequestStats(factory, _clock(scope)).execute(rows)
    except Exception:
        logger.warning("Could not store %d request-metric rows", len(rows), exc_info=True)
