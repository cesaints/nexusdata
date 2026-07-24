"""Unit of Work — transação atômica que agrega todos os repositórios."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusdata.domain.exceptions import DuplicateEntityError
from nexusdata.domain.repositories import (
    ApiKeyRepository,
    DocumentRepository,
    ProcessingJobRepository,
    TenantRepository,
    UserRepository,
    WebhookRepository,
)
from nexusdata.infrastructure.repositories import (
    SqlAlchemyApiKeyRepository,
    SqlAlchemyDocumentRepository,
    SqlAlchemyProcessingJobRepository,
    SqlAlchemyTenantRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyWebhookRepository,
)


class SqlAlchemyUnitOfWork:
    """Implementa o port UnitOfWork sobre uma AsyncSession dedicada.

    Cada instância tem sua própria sessão/transação. Violações de constraint
    (unicidade) viram `DuplicateEntityError` — a integridade é garantida pelo
    banco, não apenas por checagens de aplicação (defesa contra corridas).
    """

    # Anotados com os Protocols do domínio (não com os tipos concretos): atributos
    # de Protocol são invariantes, então o tipo declarado tem de ser a interface.
    tenants: TenantRepository
    users: UserRepository
    api_keys: ApiKeyRepository
    documents: DocumentRepository
    jobs: ProcessingJobRepository
    webhooks: WebhookRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork usada fora do 'async with'")
        return self._session

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.tenants = SqlAlchemyTenantRepository(self._session)
        self.users = SqlAlchemyUserRepository(self._session)
        self.api_keys = SqlAlchemyApiKeyRepository(self._session)
        self.documents = SqlAlchemyDocumentRepository(self._session)
        self.jobs = SqlAlchemyProcessingJobRepository(self._session)
        self.webhooks = SqlAlchemyWebhookRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                await self.session.rollback()
        finally:
            await self.session.close()
            self._session = None

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as err:
            await self.session.rollback()
            raise DuplicateEntityError("violação de restrição de unicidade") from err

    async def rollback(self) -> None:
        await self.session.rollback()


class SqlAlchemyUnitOfWorkFactory:
    """Callable que cria uma UoW nova (com sessão própria) por invocação."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)
