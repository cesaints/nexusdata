"""Schemas HTTP de entrada (request bodies).

Todos com `extra="forbid"`: campos desconhecidos são REJEITADOS (superfície de
ataque menor e contratos explícitos). O `tenant_id`/`submitted_by` NUNCA vêm do
corpo — são derivados do principal autenticado.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from nexusdata.domain.value_objects.enums import (
    ApiKeyScope,
    DocumentType,
    WebhookEventType,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterTenantRequest(_StrictModel):
    tenant_name: str = Field(min_length=2, max_length=120)
    tenant_slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9-]+$")
    admin_email: EmailStr
    admin_password: str = Field(min_length=12, max_length=128)


class LoginRequest(_StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(_StrictModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class IngestDocumentRequest(_StrictModel):
    doc_type: DocumentType = DocumentType.GENERIC
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=127)
    size_bytes: int = Field(default=0, ge=0, le=1_073_741_824)  # <= 1 GiB (metadado)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    storage_key: str | None = Field(default=None, max_length=512)
    raw_payload: dict[str, object] | None = None


class CreateApiKeyRequest(_StrictModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[ApiKeyScope] = Field(min_length=1)
    expires_at: datetime | None = None


class RegisterWebhookRequest(_StrictModel):
    url: HttpUrl
    events: list[WebhookEventType] = Field(min_length=1)
