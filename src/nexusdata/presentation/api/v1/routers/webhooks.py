"""Endpoints de gestão de webhooks (somente admin via JWT)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from nexusdata.application.dto.webhooks import (
    RegisteredWebhook,
    RegisterWebhookCommand,
    WebhookView,
)
from nexusdata.presentation.api.deps import AdminDep, ContainerDep
from nexusdata.presentation.api.schemas import RegisterWebhookRequest

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Registra um webhook (o secret HMAC é exibido UMA única vez)",
)
async def register_webhook(
    body: RegisterWebhookRequest, auth: AdminDep, container: ContainerDep
) -> RegisteredWebhook:
    command = RegisterWebhookCommand(
        tenant_id=auth.tenant_id, url=body.url, events=frozenset(body.events)
    )
    return await container.webhook_management.register(command, auth=auth)


@router.get("", summary="Lista os webhooks do tenant")
async def list_webhooks(auth: AdminDep, container: ContainerDep) -> list[WebhookView]:
    return await container.webhook_management.list(auth=auth)


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um webhook",
)
async def delete_webhook(webhook_id: UUID, auth: AdminDep, container: ContainerDep) -> None:
    await container.webhook_management.delete(webhook_id, auth=auth)
