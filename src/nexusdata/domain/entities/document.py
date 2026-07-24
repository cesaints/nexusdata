"""Entidade Document — payload não estruturado recebido para processamento."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from nexusdata.domain.value_objects.enums import DocumentType


@dataclass(slots=True, kw_only=True)
class Document:
    """Documento submetido por um tenant.

    Guarda apenas metadados e um ponteiro para o conteúdo (`storage_key`) ou o
    payload estruturado bruto (`raw_payload`). O conteúdo pesado não deve
    trafegar pela fila — apenas a referência.
    """

    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID
    submitted_by: UUID
    doc_type: DocumentType = DocumentType.GENERIC
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int = 0
    checksum_sha256: str | None = None
    storage_key: str | None = None
    raw_payload: dict[str, object] | None = None
    created_at: datetime | None = None
