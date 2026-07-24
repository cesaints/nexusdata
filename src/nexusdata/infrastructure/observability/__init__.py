"""Observabilidade: logs estruturados, métricas e tracing."""

from nexusdata.infrastructure.observability.logging import (
    bind_correlation_id,
    configure_logging,
    get_correlation_id,
)
from nexusdata.infrastructure.observability.metrics import (
    observe_http_request,
    record_job_processed,
    render_metrics,
)

__all__ = [
    "bind_correlation_id",
    "configure_logging",
    "get_correlation_id",
    "observe_http_request",
    "record_job_processed",
    "render_metrics",
]
