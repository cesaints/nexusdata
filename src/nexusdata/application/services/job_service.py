"""Caso de uso de consulta de jobs (polling)."""

from __future__ import annotations

from uuid import UUID

from nexusdata.application.dto.common import AuthContext, AuthMethod
from nexusdata.application.dto.jobs import JobView
from nexusdata.application.ports import UnitOfWorkFactory
from nexusdata.domain.exceptions import (
    AuthorizationError,
    EntityNotFoundError,
)
from nexusdata.domain.value_objects.enums import ApiKeyScope, JobStatus


class JobQueryService:
    """Leitura de jobs, sempre escopada ao tenant do principal autenticado."""

    def __init__(self, *, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get(self, job_id: UUID, *, auth: AuthContext) -> JobView:
        self._authorize_read(auth)
        async with self._uow_factory() as uow:
            job = await uow.jobs.get(auth.tenant_id, job_id)
        if job is None:
            # 404 (não 403) para não revelar existência de recurso de outro tenant.
            raise EntityNotFoundError("job não encontrado")
        return JobView.from_entity(job)

    async def list(
        self,
        *,
        auth: AuthContext,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobView]:
        self._authorize_read(auth)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        async with self._uow_factory() as uow:
            jobs = await uow.jobs.list_by_tenant(
                auth.tenant_id, status=status, limit=limit, offset=offset
            )
        return [JobView.from_entity(j) for j in jobs]

    @staticmethod
    def _authorize_read(auth: AuthContext) -> None:
        if auth.method is AuthMethod.API_KEY and (ApiKeyScope.JOBS_READ not in auth.scopes):
            raise AuthorizationError("API key sem escopo jobs:read")
