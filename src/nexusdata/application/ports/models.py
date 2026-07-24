"""Estruturas de dados retornadas/consumidas pelos ports."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from nexusdata.domain.value_objects.enums import Role


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Claims validadas extraídas de um JWT."""

    user_id: UUID
    tenant_id: UUID
    role: Role
    token_type: str  # "access" | "refresh"
    jti: str


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    """Resultado da geração de uma API key.

    `full_key` é o segredo em claro — exibido UMA vez ao cliente e descartado.
    Apenas `prefix` e `secret_hash` são persistidos.
    """

    full_key: str
    prefix: str
    secret_hash: str
