"""Fakes in-memory que implementam os ports — testes sem Docker.

Reproduzem o comportamento observável dos adapters reais (repos, UoW, clock,
publisher, notifier), permitindo exercitar domínio + aplicação + apresentação
com fidelidade e velocidade.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from fakeredis import FakeAsyncRedis

from nexusdata.application.services import (
    ApiKeyManagementService,
    AuthService,
    DocumentIngestionService,
    DocumentProcessingService,
    JobQueryService,
    WebhookManagementService,
)
from nexusdata.domain.entities import (
    ApiKey,
    Document,
    ProcessingJob,
    Tenant,
    User,
    WebhookEndpoint,
)
from nexusdata.domain.value_objects.enums import JobStatus, WebhookEventType
from nexusdata.infrastructure.ai.mock_processor import MockDocumentProcessor
from nexusdata.infrastructure.cache import IdempotencyStore
from nexusdata.infrastructure.config import Settings
from nexusdata.infrastructure.security import (
    ApiKeyServiceImpl,
    Argon2PasswordHasher,
    HmacWebhookSigner,
    JwtTokenService,
)


class FakeClock:
    def __init__(self, fixed: datetime | None = None) -> None:
        # Ancorado no tempo real por padrão: o PyJWT valida exp/nbf contra o
        # relógio real, então tokens emitidos precisam ter validade coerente.
        self._now = fixed or datetime.now(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)


@dataclass
class FakeDatabase:
    tenants: dict[UUID, Tenant] = field(default_factory=dict)
    users: dict[UUID, User] = field(default_factory=dict)
    api_keys: dict[UUID, ApiKey] = field(default_factory=dict)
    documents: dict[UUID, Document] = field(default_factory=dict)
    jobs: dict[UUID, ProcessingJob] = field(default_factory=dict)
    webhooks: dict[UUID, WebhookEndpoint] = field(default_factory=dict)


def _clone(obj: Any) -> Any:
    return copy.deepcopy(obj)


class _TenantRepo:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    async def add(self, tenant: Tenant) -> Tenant:
        self.db.tenants[tenant.id] = _clone(tenant)
        return tenant

    async def get(self, tenant_id: UUID) -> Tenant | None:
        return _clone(self.db.tenants.get(tenant_id))

    async def get_by_slug(self, slug: str) -> Tenant | None:
        for t in self.db.tenants.values():
            if t.slug == slug:
                return _clone(t)
        return None


class _UserRepo:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    async def add(self, user: User) -> User:
        self.db.users[user.id] = _clone(user)
        return user

    async def get(self, tenant_id: UUID, user_id: UUID) -> User | None:
        u = self.db.users.get(user_id)
        return _clone(u) if u and u.tenant_id == tenant_id else None

    async def get_by_email(self, email: str) -> User | None:
        for u in self.db.users.values():
            if u.email.lower() == email.lower():
                return _clone(u)
        return None

    async def list_by_tenant(self, tenant_id: UUID) -> list[User]:
        return [_clone(u) for u in self.db.users.values() if u.tenant_id == tenant_id]


class _ApiKeyRepo:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    async def add(self, api_key: ApiKey) -> ApiKey:
        self.db.api_keys[api_key.id] = _clone(api_key)
        return api_key

    async def get_by_prefix(self, prefix: str) -> ApiKey | None:
        for k in self.db.api_keys.values():
            if k.prefix == prefix:
                return _clone(k)
        return None

    async def list_by_tenant(self, tenant_id: UUID) -> list[ApiKey]:
        return [_clone(k) for k in self.db.api_keys.values() if k.tenant_id == tenant_id]

    async def touch_last_used(self, api_key_id: UUID) -> None:
        k = self.db.api_keys.get(api_key_id)
        if k:
            k.last_used_at = datetime.now(UTC)

    async def revoke(self, tenant_id: UUID, api_key_id: UUID) -> bool:
        k = self.db.api_keys.get(api_key_id)
        if k and k.tenant_id == tenant_id:
            k.is_active = False
            return True
        return False


class _DocumentRepo:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    async def add(self, document: Document) -> Document:
        self.db.documents[document.id] = _clone(document)
        return document

    async def get(self, tenant_id: UUID, document_id: UUID) -> Document | None:
        d = self.db.documents.get(document_id)
        return _clone(d) if d and d.tenant_id == tenant_id else None


class _JobRepo:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    async def add(self, job: ProcessingJob) -> ProcessingJob:
        self.db.jobs[job.id] = _clone(job)
        return job

    async def get(self, tenant_id: UUID, job_id: UUID) -> ProcessingJob | None:
        j = self.db.jobs.get(job_id)
        return _clone(j) if j and j.tenant_id == tenant_id else None

    async def get_for_update(self, job_id: UUID) -> ProcessingJob | None:
        return _clone(self.db.jobs.get(job_id))

    async def update(self, job: ProcessingJob) -> ProcessingJob:
        self.db.jobs[job.id] = _clone(job)
        return job

    async def find_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: str
    ) -> ProcessingJob | None:
        for j in self.db.jobs.values():
            if j.tenant_id == tenant_id and j.idempotency_key == idempotency_key:
                return _clone(j)
        return None

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        *,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProcessingJob]:
        items = [j for j in self.db.jobs.values() if j.tenant_id == tenant_id]
        if status is not None:
            items = [j for j in items if j.status is status]
        items.sort(key=lambda j: j.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)
        return [_clone(j) for j in items[offset : offset + limit]]

    async def count_by_status(self, status: JobStatus) -> int:
        return sum(1 for j in self.db.jobs.values() if j.status is status)


class _WebhookRepo:
    def __init__(self, db: FakeDatabase) -> None:
        self.db = db

    async def add(self, endpoint: WebhookEndpoint) -> WebhookEndpoint:
        self.db.webhooks[endpoint.id] = _clone(endpoint)
        return endpoint

    async def list_by_tenant(self, tenant_id: UUID) -> list[WebhookEndpoint]:
        return [_clone(w) for w in self.db.webhooks.values() if w.tenant_id == tenant_id]

    async def list_subscribers(
        self, tenant_id: UUID, event: WebhookEventType
    ) -> list[WebhookEndpoint]:
        return [
            _clone(w)
            for w in self.db.webhooks.values()
            if w.tenant_id == tenant_id and w.is_active and event in w.events
        ]

    async def delete(self, tenant_id: UUID, endpoint_id: UUID) -> bool:
        w = self.db.webhooks.get(endpoint_id)
        if w and w.tenant_id == tenant_id:
            del self.db.webhooks[endpoint_id]
            return True
        return False


class _FakeSession:
    async def execute(self, *_: Any, **__: Any) -> None:
        return None


class InMemoryUnitOfWork:
    def __init__(self, db: FakeDatabase) -> None:
        self._db = db
        self.session = _FakeSession()
        self.tenants = _TenantRepo(db)
        self.users = _UserRepo(db)
        self.api_keys = _ApiKeyRepo(db)
        self.documents = _DocumentRepo(db)
        self.jobs = _JobRepo(db)
        self.webhooks = _WebhookRepo(db)
        self.committed = False

    async def __aenter__(self) -> InMemoryUnitOfWork:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        return None


class InMemoryUnitOfWorkFactory:
    def __init__(self, db: FakeDatabase) -> None:
        self._db = db

    def __call__(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self._db)


class RecordingPublisher:
    def __init__(self) -> None:
        self.jobs: list[tuple[UUID, UUID]] = []
        self.webhook_events: list[tuple[UUID, str, UUID]] = []

    def publish_document_job(self, *, job_id: UUID, tenant_id: UUID) -> None:
        self.jobs.append((job_id, tenant_id))

    def publish_webhook_event(self, *, tenant_id: UUID, event: str, job_id: UUID) -> None:
        self.webhook_events.append((tenant_id, event, job_id))


class RecordingNotifier:
    def __init__(self) -> None:
        self.updates: list[tuple[UUID, str]] = []

    async def notify_job_update(self, *, tenant_id: UUID, job: ProcessingJob) -> None:
        self.updates.append((tenant_id, job.status.value))


class NoopRateLimiter:
    async def check(self, *, key: str, limit: int, window_seconds: int) -> Any:
        return SimpleNamespace(
            allowed=True, limit=limit, remaining=limit - 1, retry_after_seconds=0
        )


def build_test_container(settings: Settings) -> SimpleNamespace:
    """Monta um container com segurança/serviços REAIS sobre infra in-memory."""
    db = FakeDatabase()
    clock = FakeClock()
    uow_factory = InMemoryUnitOfWorkFactory(db)
    redis = FakeAsyncRedis(decode_responses=True)

    token_service = JwtTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        access_ttl_minutes=settings.access_token_expire_minutes,
        refresh_ttl_days=settings.refresh_token_expire_days,
        clock=clock,
    )
    hasher = Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)  # rápido em teste
    api_key_service = ApiKeyServiceImpl()
    publisher = RecordingPublisher()
    notifier = RecordingNotifier()
    processor = MockDocumentProcessor()

    return SimpleNamespace(
        settings=settings,
        clock=clock,
        db=db,
        uow_factory=uow_factory,
        redis=redis,
        idempotency=IdempotencyStore(redis),
        rate_limiter=NoopRateLimiter(),
        token_service=token_service,
        api_key_service=api_key_service,
        hmac_signer=HmacWebhookSigner(),
        publisher=publisher,
        notifier=notifier,
        processor=processor,
        auth_service=AuthService(
            uow_factory=uow_factory,
            hasher=hasher,
            tokens=token_service,
            clock=clock,
            access_ttl_seconds=settings.access_token_expire_minutes * 60,
        ),
        document_service=DocumentIngestionService(
            uow_factory=uow_factory, publisher=publisher, clock=clock
        ),
        job_service=JobQueryService(uow_factory=uow_factory),
        api_key_management=ApiKeyManagementService(
            uow_factory=uow_factory, api_keys=api_key_service, clock=clock
        ),
        webhook_management=WebhookManagementService(uow_factory=uow_factory, clock=clock),
        processing_service=DocumentProcessingService(
            uow_factory=uow_factory,
            processor=processor,
            publisher=publisher,
            notifier=notifier,
            clock=clock,
        ),
    )
