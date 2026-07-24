"""Dependências do FastAPI — DI do container e autenticação/autorização.

Suporta dois métodos de autenticação:
  * Bearer JWT (usuários do dashboard) — `Authorization: Bearer <token>`.
  * API Key (integrações M2M)       — `X-API-Key: nxk_<prefix>.<secret>`.

Ambas resultam num `AuthContext` imutável, a ÚNICA fonte de verdade para
tenant e permissões dali em diante.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from nexusdata.application.dto.common import AuthContext, AuthMethod
from nexusdata.domain.exceptions import AuthenticationError, AuthorizationError
from nexusdata.domain.value_objects.enums import Role
from nexusdata.infrastructure.container import Container
from nexusdata.infrastructure.security.api_keys import ApiKeyServiceImpl

_bearer_scheme = HTTPBearer(auto_error=False, description="JWT de acesso")
_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

# Hash dummy para verificação em tempo constante quando a chave não existe.
_DUMMY_KEY_HASH = hashlib.sha256(b"nexusdata-nonexistent-key").hexdigest()


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


async def get_auth_context(
    container: Annotated[Container, Depends(get_container)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
    api_key: Annotated[str | None, Depends(_api_key_scheme)] = None,
) -> AuthContext:
    if bearer is not None:
        return _authenticate_bearer(container, bearer.credentials)
    if api_key:
        return await _authenticate_api_key(container, api_key)
    raise AuthenticationError("credenciais ausentes")


def _authenticate_bearer(container: Container, token: str) -> AuthContext:
    claims = container.token_service.decode(token)
    if claims.token_type != "access":  # noqa: S105 - tipo de token, não senha
        raise AuthenticationError("tipo de token inválido para acesso")
    return AuthContext(
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
        role=claims.role,
        method=AuthMethod.JWT,
    )


async def _authenticate_api_key(container: Container, raw_key: str) -> AuthContext:
    api_keys: ApiKeyServiceImpl = container.api_key_service
    prefix, secret = api_keys.split(raw_key)  # AuthenticationError se malformada

    async with container.uow_factory() as uow:
        key = await uow.api_keys.get_by_prefix(prefix)

    # Verificação em tempo constante mesmo se a chave não existir.
    reference_hash = key.key_hash if key is not None else _DUMMY_KEY_HASH
    secret_ok = api_keys.verify(secret, reference_hash)
    now = container.clock.now()
    if key is None or not secret_ok or not key.is_usable(now):
        raise AuthenticationError("API key inválida")

    # Marca último uso (best-effort; não bloqueia a request se falhar).
    try:
        async with container.uow_factory() as uow:
            await uow.api_keys.touch_last_used(key.id)
            await uow.commit()
    except Exception:  # noqa: S110 - telemetria best-effort
        pass

    return AuthContext(
        user_id=None,
        tenant_id=key.tenant_id,
        role=Role.USER,
        method=AuthMethod.API_KEY,
        scopes=key.scopes,
    )


async def require_admin(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    if auth.method is not AuthMethod.JWT or not auth.is_admin:
        raise AuthorizationError("requer administrador autenticado por JWT")
    return auth


AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
AdminDep = Annotated[AuthContext, Depends(require_admin)]
ContainerDep = Annotated[Container, Depends(get_container)]
