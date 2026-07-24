"""Caso de uso de gestão de API keys (apenas admin via JWT)."""

from __future__ import annotations

from uuid import UUID

from nexusdata.application.dto.api_keys import (
    ApiKeyView,
    CreateApiKeyCommand,
    CreatedApiKey,
)
from nexusdata.application.dto.common import AuthContext, AuthMethod
from nexusdata.application.ports import ApiKeyService, Clock, UnitOfWorkFactory
from nexusdata.domain.entities import ApiKey
from nexusdata.domain.exceptions import AuthorizationError, EntityNotFoundError


class ApiKeyManagementService:
    """Cria, lista e revoga API keys. Somente administradores (autenticados por
    JWT) podem gerenciar chaves — uma API key não emite outra API key."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        api_keys: ApiKeyService,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._api_keys = api_keys
        self._clock = clock

    async def create(self, command: CreateApiKeyCommand, *, auth: AuthContext) -> CreatedApiKey:
        self._require_admin(auth)
        if command.tenant_id != auth.tenant_id:
            raise AuthorizationError("tenant divergente")

        generated = self._api_keys.generate()
        entity = ApiKey(
            tenant_id=auth.tenant_id,
            name=command.name,
            prefix=generated.prefix,
            key_hash=generated.secret_hash,
            scopes=command.scopes,
            expires_at=command.expires_at,
            created_at=self._clock.now(),
        )
        async with self._uow_factory() as uow:
            await uow.api_keys.add(entity)
            await uow.commit()

        return CreatedApiKey(
            id=entity.id,
            name=entity.name,
            prefix=entity.prefix,
            full_key=generated.full_key,  # exibido uma única vez
            scopes=entity.scopes,
            expires_at=entity.expires_at,
        )

    async def list(self, *, auth: AuthContext) -> list[ApiKeyView]:
        self._require_admin(auth)
        async with self._uow_factory() as uow:
            keys = await uow.api_keys.list_by_tenant(auth.tenant_id)
        return [
            ApiKeyView(
                id=k.id,
                name=k.name,
                prefix=k.prefix,
                scopes=k.scopes,
                is_active=k.is_active,
                last_used_at=k.last_used_at,
                expires_at=k.expires_at,
            )
            for k in keys
        ]

    async def revoke(self, api_key_id: UUID, *, auth: AuthContext) -> None:
        self._require_admin(auth)
        async with self._uow_factory() as uow:
            revoked = await uow.api_keys.revoke(auth.tenant_id, api_key_id)
            await uow.commit()
        if not revoked:
            raise EntityNotFoundError("API key não encontrada")

    @staticmethod
    def _require_admin(auth: AuthContext) -> None:
        if auth.method is not AuthMethod.JWT or not auth.is_admin:
            raise AuthorizationError("requer administrador autenticado por JWT")
