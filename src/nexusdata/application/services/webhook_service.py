"""Caso de uso de gestão de webhooks (apenas admin via JWT)."""

from __future__ import annotations

import secrets
from uuid import UUID

from nexusdata.application.dto.common import AuthContext, AuthMethod
from nexusdata.application.dto.webhooks import (
    RegisteredWebhook,
    RegisterWebhookCommand,
    WebhookView,
)
from nexusdata.application.ports import Clock, UnitOfWorkFactory
from nexusdata.domain.entities import WebhookEndpoint
from nexusdata.domain.exceptions import (
    AuthorizationError,
    BusinessRuleViolationError,
    EntityNotFoundError,
)

_WEBHOOK_SECRET_BYTES = 32


class WebhookManagementService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def register(
        self, command: RegisterWebhookCommand, *, auth: AuthContext
    ) -> RegisteredWebhook:
        self._require_admin(auth)
        self._validate_url(str(command.url))

        secret = secrets.token_urlsafe(_WEBHOOK_SECRET_BYTES)
        endpoint = WebhookEndpoint(
            tenant_id=auth.tenant_id,
            url=str(command.url),
            secret=secret,
            events=command.events,
            created_at=self._clock.now(),
        )
        async with self._uow_factory() as uow:
            await uow.webhooks.add(endpoint)
            await uow.commit()

        return RegisteredWebhook(
            id=endpoint.id,
            url=endpoint.url,
            events=endpoint.events,
            secret=secret,  # exibido uma única vez
        )

    async def list(self, *, auth: AuthContext) -> list[WebhookView]:
        self._require_admin(auth)
        async with self._uow_factory() as uow:
            endpoints = await uow.webhooks.list_by_tenant(auth.tenant_id)
        return [
            WebhookView(id=e.id, url=e.url, events=e.events, is_active=e.is_active)
            for e in endpoints
        ]

    async def delete(self, endpoint_id: UUID, *, auth: AuthContext) -> None:
        self._require_admin(auth)
        async with self._uow_factory() as uow:
            deleted = await uow.webhooks.delete(auth.tenant_id, endpoint_id)
            await uow.commit()
        if not deleted:
            raise EntityNotFoundError("webhook não encontrado")

    @staticmethod
    def _require_admin(auth: AuthContext) -> None:
        if auth.method is not AuthMethod.JWT or not auth.is_admin:
            raise AuthorizationError("requer administrador autenticado por JWT")

    @staticmethod
    def _validate_url(url: str) -> None:
        # Defesa anti-SSRF adicional acontece na entrega (infra). Aqui exigimos
        # HTTPS para não vazar assinatura/segredo em trânsito.
        if not url.startswith("https://"):
            raise BusinessRuleViolationError("a URL do webhook deve usar HTTPS")
