"""Endpoints operacionais: liveness, readiness e métricas Prometheus."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Response
from sqlalchemy import text

from nexusdata.domain.value_objects.enums import JobStatus
from nexusdata.infrastructure.observability.metrics import (
    render_metrics,
    set_jobs_pending,
)
from nexusdata.presentation.api.deps import ContainerDep

_log = structlog.get_logger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready", summary="Readiness probe (DB + Redis)")
async def ready(container: ContainerDep, response: Response) -> dict[str, object]:
    checks: dict[str, str] = {}
    try:
        async with container.uow_factory() as uow:
            await uow.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        _log.warning("health.db_fail", error=str(exc))
        checks["database"] = "fail"
    try:
        await container.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        _log.warning("health.redis_fail", error=str(exc))
        checks["redis"] = "fail"

    healthy = all(v == "ok" for v in checks.values())
    response.status_code = 200 if healthy else 503
    return {"status": "ready" if healthy else "degraded", "checks": checks}


@router.get("/metrics", summary="Métricas Prometheus", include_in_schema=False)
async def metrics(container: ContainerDep) -> Response:
    try:
        async with container.uow_factory() as uow:
            pending = await uow.jobs.count_by_status(JobStatus.PENDING)
        set_jobs_pending(pending)
    except Exception as exc:
        _log.warning("metrics.pending_fail", error=str(exc))
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
