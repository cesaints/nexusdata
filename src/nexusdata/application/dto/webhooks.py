"""DTOs de webhooks."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, HttpUrl

from nexusdata.application.dto.common import DTO
from nexusdata.domain.value_objects.enums import WebhookEventType


class RegisterWebhookCommand(DTO):
    tenant_id: UUID
    url: HttpUrl
    events: frozenset[WebhookEventType] = Field(min_length=1)


class RegisteredWebhook(DTO):
    """Retornado na criação — inclui o segredo (exibido uma vez)."""

    id: UUID
    url: str
    events: frozenset[WebhookEventType]
    secret: str


class WebhookView(DTO):
    id: UUID
    url: str
    events: frozenset[WebhookEventType]
    is_active: bool
