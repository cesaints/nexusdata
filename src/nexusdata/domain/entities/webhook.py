"""Entidade WebhookEndpoint — destino de notificações push do tenant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from nexusdata.domain.value_objects.enums import WebhookEventType


@dataclass(slots=True, kw_only=True)
class WebhookEndpoint:
    """URL de callback registrada por um tenant.

    O `secret` é usado para assinar cada entrega com HMAC-SHA256, permitindo
    que o cliente verifique a autenticidade da mensagem. O segredo é
    armazenado cifrado/hasheado conforme a política da infraestrutura.
    """

    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID
    url: str
    secret: str
    events: frozenset[WebhookEventType] = field(default_factory=frozenset)
    is_active: bool = True
    created_at: datetime | None = None

    def subscribes_to(self, event: WebhookEventType) -> bool:
        return self.is_active and event in self.events
