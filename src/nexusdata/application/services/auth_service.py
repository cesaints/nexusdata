"""Caso de uso de autenticação e registro de tenants."""

from __future__ import annotations

from nexusdata.application.dto.auth import (
    LoginCommand,
    RegisteredTenant,
    RegisterTenantCommand,
    TokenPair,
)
from nexusdata.application.ports import (
    Clock,
    PasswordHasher,
    TokenService,
    UnitOfWorkFactory,
)
from nexusdata.application.ports.models import TokenClaims
from nexusdata.domain.entities import Tenant, User
from nexusdata.domain.exceptions import (
    AuthenticationError,
    DuplicateEntityError,
)
from nexusdata.domain.value_objects.enums import Role

# Senha dummy para verificação em tempo constante (evita user enumeration).
_DUMMY_PASSWORD = "n3xusdata-timing-guard-constant"  # noqa: S105 - guarda de timing


class AuthService:
    """Registro de tenant, login (com tokens) e refresh.

    Regras de segurança aplicadas aqui:
      * Login não revela se o e-mail existe (sempre executa um hash-verify).
      * Access token curto (15 min) + refresh token (rotacionável).
      * Rehash transparente quando a política de custo do Argon2 muda.
    """

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        tokens: TokenService,
        clock: Clock,
        access_ttl_seconds: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock
        self._access_ttl = access_ttl_seconds
        # Custo fixo de verificação para o caminho "usuário inexistente".
        self._dummy_hash = hasher.hash(_DUMMY_PASSWORD)

    async def register_tenant(self, command: RegisterTenantCommand) -> RegisteredTenant:
        async with self._uow_factory() as uow:
            if await uow.tenants.get_by_slug(command.tenant_slug) is not None:
                raise DuplicateEntityError("slug de tenant já em uso")
            if await uow.users.get_by_email(command.admin_email) is not None:
                raise DuplicateEntityError("e-mail já cadastrado")

            tenant = Tenant(name=command.tenant_name, slug=command.tenant_slug)
            await uow.tenants.add(tenant)

            admin = User(
                tenant_id=tenant.id,
                email=command.admin_email,
                password_hash=self._hasher.hash(command.admin_password),
                role=Role.ADMIN,
            )
            await uow.users.add(admin)
            await uow.commit()

        return RegisteredTenant(tenant_id=tenant.id, admin_user_id=admin.id)

    async def login(self, command: LoginCommand) -> TokenPair:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(command.email)

            # Sempre gasta o mesmo tempo, exista o usuário ou não.
            reference_hash = user.password_hash if user else self._dummy_hash
            password_ok = self._hasher.verify(command.password, reference_hash)

            if user is None or not password_ok or not user.is_active:
                raise AuthenticationError("credenciais inválidas")

            # Rehash transparente se a política de custo mudou.
            if self._hasher.needs_rehash(user.password_hash):
                user.password_hash = self._hasher.hash(command.password)
                await uow.users.add(user)
                await uow.commit()

            return self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = self._decode_refresh(refresh_token)
        async with self._uow_factory() as uow:
            user = await uow.users.get(claims.tenant_id, claims.user_id)
            if user is None or not user.is_active:
                raise AuthenticationError("sessão inválida")
            return self._issue_tokens(user)

    def _decode_refresh(self, token: str) -> TokenClaims:
        claims = self._tokens.decode(token)
        if claims.token_type != "refresh":  # noqa: S105 - comparação de tipo, não senha
            raise AuthenticationError("token não é de refresh")
        return claims

    def _issue_tokens(self, user: User) -> TokenPair:
        access = self._tokens.create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role
        )
        refresh = self._tokens.create_refresh_token(user_id=user.id, tenant_id=user.tenant_id)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._access_ttl,
        )
