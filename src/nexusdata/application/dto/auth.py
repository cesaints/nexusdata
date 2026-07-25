"""DTOs de autenticação e registro."""

from __future__ import annotations

from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from nexusdata.application.dto.common import DTO

# Política de senha forte (validada na borda da aplicação).
_MIN_PASSWORD_LEN = 12
_MAX_PASSWORD_LEN = 128  # limite anti-DoS no hashing (Argon2)


class RegisterTenantCommand(DTO):
    tenant_name: str = Field(min_length=2, max_length=120)
    tenant_slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9-]+$")
    admin_email: EmailStr
    admin_password: str = Field(min_length=_MIN_PASSWORD_LEN, max_length=_MAX_PASSWORD_LEN)

    @field_validator("admin_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("a senha deve conter ao menos um dígito")
        if not any(c.isalpha() for c in v):
            raise ValueError("a senha deve conter ao menos uma letra")
        return v


class RegisteredTenant(DTO):
    tenant_id: UUID
    admin_user_id: UUID


class LoginCommand(DTO):
    email: EmailStr
    password: str = Field(min_length=1, max_length=_MAX_PASSWORD_LEN)


class TokenPair(DTO):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - rótulo OAuth, não é senha
    expires_in: int  # segundos
