"""DTOs comuns — contexto de autenticação e base."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from nexusdata.domain.value_objects.enums import ApiKeyScope, Role


class DTO(BaseModel):
    """Base imutável e estrita para DTOs (rejeita campos extras)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class AuthMethod(StrEnum):
    JWT = "jwt"
    API_KEY = "api_key"


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Principal autenticado, propagado da apresentação para os casos de uso.

    É a fonte da verdade para autorização: o `tenant_id` aqui é o ÚNICO tenant
    que a requisição pode tocar. Casos de uso jamais confiam em um tenant_id
    vindo do corpo/parâmetro da requisição.
    """

    user_id: UUID | None
    tenant_id: UUID
    role: Role
    method: AuthMethod
    scopes: frozenset[ApiKeyScope] = frozenset()

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN
