"""Caso de uso de processamento (executado pelo worker Celery).

Coração do sistema distribuído. Orquestra a máquina de estados do job, chama
o processador (IA plugável, já embrulhado com Circuit Breaker + Retry na infra)
e decide, em nível de job, entre concluir, reprocessar ou falhar.
"""

from __future__ import annotations

from uuid import UUID

from nexusdata.application.ports import Clock, EventPublisher, Notifier, UnitOfWorkFactory
from nexusdata.application.ports.processor import DocumentProcessor, ProcessorError
from nexusdata.domain.value_objects.enums import WebhookEventType


class RetryableProcessingError(Exception):
    """Sinaliza ao worker que ele deve reagendar a tarefa (backoff exponencial)."""

    def __init__(self, job_id: UUID, reason: str) -> None:
        super().__init__(reason)
        self.job_id = job_id
        self.reason = reason


class DocumentProcessingService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        processor: DocumentProcessor,
        publisher: EventPublisher,
        notifier: Notifier,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._processor = processor
        self._publisher = publisher
        self._notifier = notifier
        self._clock = clock

    async def process(self, job_id: UUID) -> None:
        # 1) Trava a linha do job para evitar corrida entre entregas duplicadas.
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)
            if job is None:
                return  # job desconhecido: entrega órfã, ignora com segurança.
            if job.is_terminal:
                return  # já processado (at-least-once delivery): idempotente.

            document = await uow.documents.get(job.tenant_id, job.document_id)
            if document is None:
                job.mark_failed(now=self._clock.now(), error="documento ausente")
                await uow.jobs.update(job)
                await uow.commit()
                await self._notifier.notify_job_update(tenant_id=job.tenant_id, job=job)
                return

            job.mark_processing(now=self._clock.now())
            await uow.jobs.update(job)
            await uow.commit()

        await self._notifier.notify_job_update(tenant_id=job.tenant_id, job=job)

        # 2) Processamento externo (fora da transação — pode demorar).
        try:
            result = await self._processor.process(document)
        except ProcessorError as exc:
            await self._handle_failure(job_id, reason=str(exc))
            return

        # 3) Persiste sucesso e notifica.
        async with self._uow_factory() as uow:
            fresh = await uow.jobs.get_for_update(job_id)
            if fresh is None or fresh.is_terminal:
                return
            fresh.mark_completed(
                now=self._clock.now(),
                result={
                    "extracted": result.extracted,
                    "confidence": result.confidence,
                    "provider": result.provider,
                    "model": result.model,
                    "warnings": list(result.warnings),
                },
            )
            await uow.jobs.update(fresh)
            await uow.commit()

        await self._notifier.notify_job_update(tenant_id=fresh.tenant_id, job=fresh)
        self._publisher.publish_webhook_event(
            tenant_id=fresh.tenant_id,
            event=WebhookEventType.JOB_COMPLETED.value,
            job_id=fresh.id,
        )

    async def _handle_failure(self, job_id: UUID, *, reason: str) -> None:
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)
            if job is None or job.is_terminal:
                return

            if job.can_retry:
                job.mark_retrying(now=self._clock.now(), reason=reason)
                await uow.jobs.update(job)
                await uow.commit()
                await self._notifier.notify_job_update(tenant_id=job.tenant_id, job=job)
                # Deixa o worker reagendar com backoff exponencial.
                raise RetryableProcessingError(job_id, reason)

            job.mark_failed(now=self._clock.now(), error=reason)
            await uow.jobs.update(job)
            await uow.commit()

        await self._notifier.notify_job_update(tenant_id=job.tenant_id, job=job)
        self._publisher.publish_webhook_event(
            tenant_id=job.tenant_id,
            event=WebhookEventType.JOB_FAILED.value,
            job_id=job.id,
        )
