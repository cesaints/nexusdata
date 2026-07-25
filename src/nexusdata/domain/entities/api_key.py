"""Entidade ApiKey — autenticação máquina-a-máquina por escopos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from nexusdata.domain.value_objects.enums import ApiKeyScope


@dataclass(slots=True, kw_only=True)
class ApiKey:
    """Chave de API de um tenant.

    Segurança: apenas o hash da chave é persistido (`key_hash`). O segredo em
    claro é exibido UMA única vez, no momento da criação, e nunca mais.
    O `prefix` (não secreto) permite localizar a chave sem revelar o segredo.
    """

    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID
    name: str
    prefix: str
    key_hash: str
    scopes: frozenset[ApiKeyScope] = field(default_factory=frozenset)
    is_active: bool = True
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None

    def has_scope(self, scope: ApiKeyScope) -> bool:
        return scope in self.scopes

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def is_usable(self, now: datetime) -> bool:
        return self.is_active and not self.is_expired(now)
