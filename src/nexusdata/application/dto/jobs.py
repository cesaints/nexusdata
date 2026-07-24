"""DTOs de consulta de jobs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from nexusdata.application.dto.common import DTO
from nexusdata.domain.entities import ProcessingJob
from nexusdata.domain.value_objects.enums import JobStatus


class JobView(DTO):
    id: UUID
    document_id: UUID
    status: JobStatus
    attempts: int
    max_attempts: int
    result: dict[str, object] | None
    error: str | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_entity(cls, job: ProcessingJob) -> JobView:
        return cls(
            id=job.id,
            document_id=job.document_id,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            result=job.result,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
