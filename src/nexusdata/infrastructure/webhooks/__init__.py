"""Entrega de webhooks (HTTP push assinado com HMAC)."""

from nexusdata.infrastructure.webhooks.dispatcher import (
    WebhookDeliveryError,
    WebhookDispatcher,
)

__all__ = ["WebhookDeliveryError", "WebhookDispatcher"]
