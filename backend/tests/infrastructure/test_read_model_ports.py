"""Every read-model port is fully implemented by its SQL adapter and its in-memory fake.

The application tests run against the fakes, so a method missing only from the SQL adapter
would pass the suite and fail in production (it happened once with ``tenant_counts``).
"""

from __future__ import annotations

import pytest

from medicore.application.ports.unit_of_work import (
    ErrorLogRepository,
    JobLogRepository,
    LoginThrottleRepository,
    MonitoringReadModel,
    PlatformReadModel,
    RequestStatsRepository,
)
from medicore.domain.repositories import FeeScheduleRepository
from medicore.infrastructure.persistence.repositories.fee_schedule import SqlFeeScheduleRepository
from medicore.infrastructure.persistence.repositories.login_throttle import (
    SqlLoginThrottleRepository,
)
from medicore.infrastructure.persistence.repositories.monitoring import (
    SqlErrorLogRepository,
    SqlJobLogRepository,
    SqlMonitoringReadModel,
    SqlRequestStatsRepository,
)
from medicore.infrastructure.persistence.repositories.platform_reads import SqlPlatformReadModel
from tests.support.repositories import (
    InMemoryErrorLogRepository,
    InMemoryFeeScheduleRepository,
    InMemoryJobLogRepository,
    InMemoryLoginThrottleRepository,
    InMemoryMonitoringReadModel,
    InMemoryPlatformReadModel,
    InMemoryRequestStatsRepository,
)


def _methods(port) -> set[str]:
    return {
        name for name in vars(port)
        if not name.startswith("_") and callable(getattr(port, name))
    }


@pytest.mark.parametrize(
    ("port", "adapters"),
    [
        (PlatformReadModel, (SqlPlatformReadModel, InMemoryPlatformReadModel)),
        (MonitoringReadModel, (SqlMonitoringReadModel, InMemoryMonitoringReadModel)),
        (ErrorLogRepository, (SqlErrorLogRepository, InMemoryErrorLogRepository)),
        (JobLogRepository, (SqlJobLogRepository, InMemoryJobLogRepository)),
        (RequestStatsRepository, (SqlRequestStatsRepository, InMemoryRequestStatsRepository)),
        (FeeScheduleRepository, (SqlFeeScheduleRepository, InMemoryFeeScheduleRepository)),
        (LoginThrottleRepository, (SqlLoginThrottleRepository, InMemoryLoginThrottleRepository)),
    ],
)
def test_adapters_implement_the_whole_port(port, adapters):
    for adapter in adapters:
        missing = _methods(port) - _methods(adapter)
        assert not missing, f"{adapter.__name__} lacks {sorted(missing)}"
