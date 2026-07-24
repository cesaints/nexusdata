"""Endpoints de gestão de API keys (somente admin via JWT)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from nexusdata.application.dto.api_keys import (
    ApiKeyView,
    CreateApiKeyCommand,
    CreatedApiKey,
)
from nexusdata.presentation.api.deps import AdminDep, ContainerDep
from nexusdata.presentation.api.schemas import CreateApiKeyRequest

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma API key (o segredo é exibido UMA única vez)",
)
async def create_api_key(
    body: CreateApiKeyRequest, auth: AdminDep, container: ContainerDep
) -> CreatedApiKey:
    command = CreateApiKeyCommand(
        tenant_id=auth.tenant_id,
        name=body.name,
        scopes=frozenset(body.scopes),
        expires_at=body.expires_at,
    )
    return await container.api_key_management.create(command, auth=auth)


@router.get("", summary="Lista as API keys do tenant (sem segredos)")
async def list_api_keys(auth: AdminDep, container: ContainerDep) -> list[ApiKeyView]:
    return await container.api_key_management.list(auth=auth)


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoga uma API key",
)
async def revoke_api_key(api_key_id: UUID, auth: AdminDep, container: ContainerDep) -> None:
    await container.api_key_management.revoke(api_key_id, auth=auth)
