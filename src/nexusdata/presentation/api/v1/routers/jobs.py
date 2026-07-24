"""Endpoints de consulta de jobs (polling)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from nexusdata.application.dto.jobs import JobView
from nexusdata.domain.value_objects.enums import JobStatus
from nexusdata.presentation.api.deps import AuthDep, ContainerDep

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", summary="Consulta o status de um job")
async def get_job(job_id: UUID, auth: AuthDep, container: ContainerDep) -> JobView:
    return await container.job_service.get(job_id, auth=auth)


@router.get("", summary="Lista jobs do tenant (paginado, filtrável por status)")
async def list_jobs(
    auth: AuthDep,
    container: ContainerDep,
    status: JobStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[JobView]:
    return await container.job_service.list(auth=auth, status=status, limit=limit, offset=offset)
