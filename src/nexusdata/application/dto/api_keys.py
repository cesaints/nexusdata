"""DTOs de API keys."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from nexusdata.application.dto.common import DTO
from nexusdata.domain.value_objects.enums import ApiKeyScope


class CreateApiKeyCommand(DTO):
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=120)
    scopes: frozenset[ApiKeyScope] = Field(min_length=1)
    expires_at: datetime | None = None


class CreatedApiKey(DTO):
    """Retornado UMA vez na criação — contém o segredo em claro."""

    id: UUID
    name: str
    prefix: str
    full_key: str
    scopes: frozenset[ApiKeyScope]
    expires_at: datetime | None


class ApiKeyView(DTO):
    """Representação segura (sem segredo) para listagem."""

    id: UUID
    name: str
    prefix: str
    scopes: frozenset[ApiKeyScope]
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
