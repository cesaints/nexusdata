"""Entidade Tenant — unidade de isolamento multi-tenant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(slots=True, kw_only=True)
class Tenant:
    """Cliente da plataforma. Raiz do isolamento de dados.

    Todo recurso (usuários, documentos, jobs, webhooks) pertence a exatamente
    um tenant. Nenhuma query de negócio deve cruzar a fronteira do tenant.
    """

    id: UUID = field(default_factory=uuid4)
    name: str
    slug: str
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def deactivate(self) -> None:
        self.is_active = False
