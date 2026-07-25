"""Publisher de eventos via Celery/RabbitMQ (implementa EventPublisher)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from nexusdata.infrastructure.messaging.task_names import (
    QUEUE_DOCUMENTS,
    QUEUE_WEBHOOKS,
    TASK_DELIVER_WEBHOOK,
    TASK_PROCESS_DOCUMENT,
)

if TYPE_CHECKING:
    from celery import Celery


class CeleryEventPublisher:
    """Envia tarefas por NOME (send_task) — desacopla o publisher do código do
    worker (a API não precisa importar as tasks)."""

    def __init__(self, celery_app: Celery) -> None:
        self._celery = celery_app

    def publish_document_job(self, *, job_id: UUID, tenant_id: UUID) -> None:
        self._celery.send_task(
            TASK_PROCESS_DOCUMENT,
            kwargs={"job_id": str(job_id), "tenant_id": str(tenant_id)},
            queue=QUEUE_DOCUMENTS,
        )

    def publish_webhook_event(self, *, tenant_id: UUID, event: str, job_id: UUID) -> None:
        self._celery.send_task(
            TASK_DELIVER_WEBHOOK,
            kwargs={
                "tenant_id": str(tenant_id),
                "event": event,
                "job_id": str(job_id),
            },
            queue=QUEUE_WEBHOOKS,
        )
