"""Entidade User."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from nexusdata.domain.value_objects.enums import Role


@dataclass(slots=True, kw_only=True)
class User:
    """Usuário pertencente a um tenant.

    O `password_hash` guarda apenas o hash Argon2id — a senha em claro nunca
    trafega no domínio nem é persistida.
    """

    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID
    email: str
    password_hash: str
    role: Role = Role.USER
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN
