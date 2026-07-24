"""Entidade ProcessingJob — máquina de estados do processamento assíncrono."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from nexusdata.domain.exceptions import InvalidStateTransitionError
from nexusdata.domain.value_objects.enums import JobStatus

# Transições permitidas na máquina de estados.
_ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.PROCESSING, JobStatus.FAILED}),
    JobStatus.PROCESSING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.RETRYING}),
    JobStatus.RETRYING: frozenset({JobStatus.PROCESSING, JobStatus.FAILED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.FAILED: frozenset(),
}


@dataclass(slots=True, kw_only=True)
class ProcessingJob:
    """Job que rastreia o processamento de um documento.

    A entidade é a fonte da verdade das transições de estado. A infraestrutura
    (worker/repositório) apenas persiste o resultado dessas transições — nunca
    escreve um status inválido diretamente.
    """

    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID
    document_id: UUID
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    result: dict[str, object] | None = None
    error: str | None = None
    idempotency_key: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None

    def _transition(self, target: JobStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidStateTransitionError(f"Transição inválida: {self.status} -> {target}")
        self.status = target

    def mark_processing(self, *, now: datetime) -> None:
        self._transition(JobStatus.PROCESSING)
        self.attempts += 1
        if self.started_at is None:
            self.started_at = now
        self.error = None
        self.updated_at = now

    def mark_retrying(self, *, now: datetime, reason: str) -> None:
        self._transition(JobStatus.RETRYING)
        self.error = reason
        self.updated_at = now

    def mark_completed(self, *, now: datetime, result: dict[str, object]) -> None:
        self._transition(JobStatus.COMPLETED)
        self.result = result
        self.error = None
        self.finished_at = now
        self.updated_at = now

    def mark_failed(self, *, now: datetime, error: str) -> None:
        self._transition(JobStatus.FAILED)
        self.error = error
        self.finished_at = now
        self.updated_at = now

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal
