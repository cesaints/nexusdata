"""Caso de uso de ingestão de documentos (produz o job assíncrono)."""

from __future__ import annotations

from nexusdata.application.dto.common import AuthContext, AuthMethod
from nexusdata.application.dto.documents import IngestDocumentCommand, IngestResult
from nexusdata.application.ports import Clock, EventPublisher, UnitOfWorkFactory
from nexusdata.domain.entities import Document, ProcessingJob
from nexusdata.domain.exceptions import AuthorizationError, TenantIsolationError
from nexusdata.domain.value_objects.enums import ApiKeyScope


class DocumentIngestionService:
    """Recebe o documento, persiste como PENDING e publica na fila.

    Responde rápido (o endpoint retorna 202). O processamento pesado ocorre no
    worker. Garantias:
      * Isolamento de tenant reforçado no serviço (defense in depth).
      * Idempotência: mesma Idempotency-Key => mesmo job, sem duplicar trabalho.
      * Publicação na fila só APÓS o commit (o dado já existe quando o worker
        consome). Se a publicação falhar, o job permanece PENDING e pode ser
        reconciliado — ver nota sobre Transactional Outbox no README.
    """

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        publisher: EventPublisher,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._clock = clock

    async def ingest(self, command: IngestDocumentCommand, *, auth: AuthContext) -> IngestResult:
        self._authorize(command, auth)

        async with self._uow_factory() as uow:
            # Idempotência: replay retorna o job existente, sem novo trabalho.
            if command.idempotency_key:
                existing = await uow.jobs.find_by_idempotency_key(
                    command.tenant_id, command.idempotency_key
                )
                if existing is not None:
                    return IngestResult(
                        job_id=existing.id,
                        document_id=existing.document_id,
                        status=existing.status,
                        idempotent_replay=True,
                    )

            now = self._clock.now()
            document = Document(
                tenant_id=command.tenant_id,
                submitted_by=command.submitted_by,
                doc_type=command.doc_type,
                filename=command.filename,
                content_type=command.content_type,
                size_bytes=command.size_bytes,
                checksum_sha256=command.checksum_sha256,
                storage_key=command.storage_key,
                raw_payload=command.raw_payload,
                created_at=now,
            )
            await uow.documents.add(document)

            job = ProcessingJob(
                tenant_id=command.tenant_id,
                document_id=document.id,
                idempotency_key=command.idempotency_key,
                created_at=now,
                updated_at=now,
            )
            await uow.jobs.add(job)
            await uow.commit()

        # Fora da transação: o dado já está durável.
        self._publisher.publish_document_job(job_id=job.id, tenant_id=job.tenant_id)

        return IngestResult(
            job_id=job.id,
            document_id=document.id,
            status=job.status,
            idempotent_replay=False,
        )

    @staticmethod
    def _authorize(command: IngestDocumentCommand, auth: AuthContext) -> None:
        if command.tenant_id != auth.tenant_id:
            raise TenantIsolationError()
        if auth.method is AuthMethod.API_KEY and (ApiKeyScope.DOCUMENTS_WRITE not in auth.scopes):
            raise AuthorizationError("API key sem escopo documents:write")
