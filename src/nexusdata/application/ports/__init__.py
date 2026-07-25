"""Ports — abstrações que os casos de uso consomem (Dependency Inversion).

Nenhum caso de uso conhece a implementação concreta (SQLAlchemy, Redis, Celery,
Argon2, PyJWT). Eles dependem apenas destes Protocols, o que torna a aplicação
testável de forma isolada e trocável de tecnologia sem tocar na regra de negócio.
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol, runtime_checkable
from uuid import UUID

from nexusdata.domain.entities import ProcessingJob
from nexusdata.domain.repositories import (
    ApiKeyRepository,
    DocumentRepository,
    ProcessingJobRepository,
    TenantRepository,
    UserRepository,
    WebhookRepository,
)
from nexusdata.domain.value_objects.enums import Role


@runtime_checkable
class Clock(Protocol):
    """Fonte de tempo injetável (torna 'now' determinístico em testes)."""

    def now(self) -> datetime: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Unit of Work — agrega repositórios numa única transação atômica.

    Uso:
        async with uow:
            await uow.jobs.add(job)
            await uow.commit()
    Se o bloco sair sem commit, a transação sofre rollback automático.
    """

    tenants: TenantRepository
    users: UserRepository
    api_keys: ApiKeyRepository
    documents: DocumentRepository
    jobs: ProcessingJobRepository
    webhooks: WebhookRepository

    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


@runtime_checkable
class UnitOfWorkFactory(Protocol):
    """Fábrica que cria uma UoW nova (com sessão própria) sob demanda."""

    def __call__(self) -> UnitOfWork: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Publica trabalho na fila (RabbitMQ via Celery)."""

    def publish_document_job(self, *, job_id: UUID, tenant_id: UUID) -> None: ...
    def publish_webhook_event(self, *, tenant_id: UUID, event: str, job_id: UUID) -> None: ...


@runtime_checkable
class PasswordHasher(Protocol):
    """Hashing de senha (Argon2id) com verificação em tempo constante."""

    def hash(self, plain: str) -> str: ...
    def verify(self, plain: str, hashed: str) -> bool: ...
    def needs_rehash(self, hashed: str) -> bool: ...


@runtime_checkable
class TokenService(Protocol):
    """Emissão/validação de JWT (access + refresh)."""

    def create_access_token(self, *, user_id: UUID, tenant_id: UUID, role: Role) -> str: ...
    def create_refresh_token(self, *, user_id: UUID, tenant_id: UUID) -> str: ...
    def decode(self, token: str) -> TokenClaims: ...


@runtime_checkable
class ApiKeyService(Protocol):
    """Geração e verificação de API keys (segredo exibido só uma vez)."""

    def generate(self) -> GeneratedApiKey: ...
    def hash_secret(self, secret: str) -> str: ...
    def verify(self, secret: str, hashed: str) -> bool: ...
    def prefix_of(self, full_key: str) -> str: ...
    def split(self, full_key: str) -> tuple[str, str]: ...


@runtime_checkable
class WebhookSigner(Protocol):
    """Assina o corpo do webhook com HMAC-SHA256."""

    def sign(self, *, secret: str, payload: bytes, timestamp: str) -> str: ...


@runtime_checkable
class Notifier(Protocol):
    """Notifica clientes em tempo real (WebSocket) sobre mudança de job."""

    async def notify_job_update(self, *, tenant_id: UUID, job: ProcessingJob) -> None: ...


# --- Estruturas de dados dos ports (import tardio evita ciclos) ---
from nexusdata.application.ports.models import (  # noqa: E402
    GeneratedApiKey,
    TokenClaims,
)

__all__ = [
    "ApiKeyService",
    "Clock",
    "EventPublisher",
    "GeneratedApiKey",
    "Notifier",
    "PasswordHasher",
    "TokenClaims",
    "TokenService",
    "UnitOfWork",
    "UnitOfWorkFactory",
    "WebhookSigner",
]
