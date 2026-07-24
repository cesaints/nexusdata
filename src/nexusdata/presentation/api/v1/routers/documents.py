"""Endpoint de ingestão de documentos (produz job assíncrono)."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Header, Response, status
from fastapi.responses import JSONResponse

from nexusdata.application.dto.documents import IngestDocumentCommand
from nexusdata.domain.exceptions import (
    AuthenticationError,
    BusinessRuleViolationError,
)
from nexusdata.infrastructure.cache.idempotency import IdempotencyOutcome, IdempotencyRecord
from nexusdata.presentation.api.deps import AuthDep, ContainerDep
from nexusdata.presentation.api.schemas import IngestDocumentRequest

router = APIRouter(prefix="/documents", tags=["documents"])

_MAX_IDEMPOTENCY_KEY_LEN = 255


@router.post(
    "/process",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Recebe um documento, enfileira o processamento e retorna 202 + job_id",
)
async def process_document(
    body: IngestDocumentRequest,
    auth: AuthDep,
    container: ContainerDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    if auth.user_id is None and auth.method.value == "jwt":  # defesa extra
        raise AuthenticationError("contexto de usuário ausente")

    if idempotency_key is not None and len(idempotency_key) > _MAX_IDEMPOTENCY_KEY_LEN:
        raise BusinessRuleViolationError("Idempotency-Key excede o tamanho máximo")

    command = IngestDocumentCommand(
        tenant_id=auth.tenant_id,
        submitted_by=auth.user_id or auth.tenant_id,
        doc_type=body.doc_type,
        filename=body.filename,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        checksum_sha256=body.checksum_sha256,
        storage_key=body.storage_key,
        raw_payload=body.raw_payload,
        idempotency_key=idempotency_key,
    )

    settings = container.settings

    # --- Sem Idempotency-Key: fluxo direto ---
    if idempotency_key is None:
        result = await container.document_service.ingest(command, auth=auth)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=json.loads(result.model_dump_json()),
        )

    # --- Com Idempotency-Key: cache de resposta no Redis (anti-duplicidade) ---
    fingerprint = _fingerprint(auth.tenant_id.hex, body)
    lookup = await container.idempotency.start(
        tenant_id=auth.tenant_id,
        key=idempotency_key,
        fingerprint=fingerprint,
        ttl_seconds=settings.idempotency_ttl_seconds,
    )

    if lookup.outcome is IdempotencyOutcome.REPLAY and lookup.record is not None:
        return JSONResponse(
            status_code=lookup.record.status_code,
            content=json.loads(lookup.record.body),
            headers={"Idempotent-Replay": "true"},
        )
    if lookup.outcome is IdempotencyOutcome.IN_PROGRESS:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "idempotency_in_progress",
                    "message": "requisição idêntica ainda em processamento",
                }
            },
        )
    if lookup.outcome is IdempotencyOutcome.CONFLICT_FINGERPRINT:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "idempotency_key_reuse",
                    "message": "Idempotency-Key reutilizada com corpo diferente",
                }
            },
        )

    # NEW: processa e grava a resposta para replays futuros.
    try:
        result = await container.document_service.ingest(command, auth=auth)
    except Exception:
        # Libera a reserva para permitir um retry legítimo do cliente.
        await container.idempotency.release(tenant_id=auth.tenant_id, key=idempotency_key)
        raise

    body_json = result.model_dump_json()
    await container.idempotency.finish(
        tenant_id=auth.tenant_id,
        key=idempotency_key,
        fingerprint=fingerprint,
        record=IdempotencyRecord(status_code=status.HTTP_202_ACCEPTED, body=body_json),
        ttl_seconds=settings.idempotency_ttl_seconds,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=json.loads(body_json))


def _fingerprint(tenant_hex: str, body: IngestDocumentRequest) -> str:
    canonical = tenant_hex + "|" + body.model_dump_json()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
