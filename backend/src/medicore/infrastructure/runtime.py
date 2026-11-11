"""RuntimeInfo adapter: version from the installed package, commit and environment from
settings, start time captured when this module is first imported (process start)."""

from __future__ import annotations

import platform
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from medicore.application.ports.runtime import RuntimeFacts
from medicore.infrastructure.config import get_settings

STARTED_AT = datetime.now(UTC)


def _version() -> str:
    try:
        return version("medicore")
    except PackageNotFoundError:  # pragma: no cover - running from a bare checkout
        return "dev"


class ProcessRuntimeInfo:
    def facts(self) -> RuntimeFacts:
        settings = get_settings()
        commit = settings.source_commit.strip() or None
        return RuntimeFacts(
            version=_version(),
            commit=commit,
            environment=settings.environment,
            python=platform.python_version(),
            started_at=STARTED_AT,
        )
