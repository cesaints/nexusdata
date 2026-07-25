"""DTOs de ingestão de documentos."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from nexusdata.application.dto.common import DTO
from nexusdata.domain.value_objects.enums import DocumentType, JobStatus


class IngestDocumentCommand(DTO):
    """Comando de ingestão. O `tenant_id`/`submitted_by` vêm do AuthContext,
    nunca do corpo da requisição (proteção contra tenant spoofing)."""

    tenant_id: UUID
    submitted_by: UUID
    doc_type: DocumentType = DocumentType.GENERIC
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=127)
    size_bytes: int = Field(default=0, ge=0)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    storage_key: str | None = Field(default=None, max_length=512)
    raw_payload: dict[str, object] | None = None
    idempotency_key: str | None = Field(default=None, max_length=255)


class IngestResult(DTO):
    job_id: UUID
    document_id: UUID
    status: JobStatus
    idempotent_replay: bool = False
