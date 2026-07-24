"""Métricas Prometheus.

Expõe: latência/contagem de requisições HTTP, jobs processados por status e
jobs pendentes na fila. O endpoint /metrics renderiza este registry.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS_TOTAL = Counter(
    "nexus_http_requests_total",
    "Total de requisições HTTP",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)
HTTP_REQUEST_DURATION = Histogram(
    "nexus_http_request_duration_seconds",
    "Duração das requisições HTTP",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
JOBS_PROCESSED_TOTAL = Counter(
    "nexus_jobs_processed_total",
    "Total de jobs finalizados por status",
    labelnames=("status",),
    registry=REGISTRY,
)
JOBS_PENDING = Gauge(
    "nexus_jobs_pending",
    "Quantidade de jobs aguardando processamento",
    registry=REGISTRY,
)
WEBHOOK_DELIVERIES_TOTAL = Counter(
    "nexus_webhook_deliveries_total",
    "Total de entregas de webhook por resultado",
    labelnames=("outcome",),
    registry=REGISTRY,
)


def observe_http_request(*, method: str, path: str, status: int, duration_seconds: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=str(status)).inc()
    HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(duration_seconds)


def record_job_processed(status: str) -> None:
    JOBS_PROCESSED_TOTAL.labels(status=status).inc()


def set_jobs_pending(count: int) -> None:
    JOBS_PENDING.set(count)


def record_webhook_delivery(outcome: str) -> None:
    WEBHOOK_DELIVERIES_TOTAL.labels(outcome=outcome).inc()


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
