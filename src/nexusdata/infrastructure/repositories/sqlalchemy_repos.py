"""Repositórios SQLAlchemy — toda leitura/escrita escopada por tenant."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexusdata.domain.entities import (
    ApiKey,
    Document,
    ProcessingJob,
    Tenant,
    User,
    WebhookEndpoint,
)
from nexusdata.domain.value_objects.enums import JobStatus, WebhookEventType
from nexusdata.infrastructure.database import mappers as mp
from nexusdata.infrastructure.database.models import (
    ApiKeyModel,
    DocumentModel,
    ProcessingJobModel,
    TenantModel,
    UserModel,
    WebhookEndpointModel,
)


class SqlAlchemyTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, tenant: Tenant) -> Tenant:
        self._s.add(mp.tenant_to_model(tenant))
        await self._s.flush()
        return tenant

    async def get(self, tenant_id: UUID) -> Tenant | None:
        m = await self._s.get(TenantModel, tenant_id)
        return mp.tenant_to_entity(m) if m else None

    async def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(TenantModel).where(TenantModel.slug == slug)
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.tenant_to_entity(m) if m else None


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, user: User) -> User:
        existing = await self._s.get(UserModel, user.id)
        if existing is not None:
            existing.password_hash = user.password_hash
            existing.role = user.role.value
            existing.is_active = user.is_active
        else:
            self._s.add(mp.user_to_model(user))
        await self._s.flush()
        return user

    async def get(self, tenant_id: UUID, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id, UserModel.tenant_id == tenant_id)
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.user_to_entity(m) if m else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(func.lower(UserModel.email) == email.lower())
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.user_to_entity(m) if m else None

    async def list_by_tenant(self, tenant_id: UUID) -> list[User]:
        stmt = select(UserModel).where(UserModel.tenant_id == tenant_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [mp.user_to_entity(m) for m in rows]


class SqlAlchemyApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, api_key: ApiKey) -> ApiKey:
        self._s.add(mp.api_key_to_model(api_key))
        await self._s.flush()
        return api_key

    async def get_by_prefix(self, prefix: str) -> ApiKey | None:
        stmt = select(ApiKeyModel).where(ApiKeyModel.prefix == prefix)
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.api_key_to_entity(m) if m else None

    async def list_by_tenant(self, tenant_id: UUID) -> list[ApiKey]:
        stmt = select(ApiKeyModel).where(ApiKeyModel.tenant_id == tenant_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [mp.api_key_to_entity(m) for m in rows]

    async def touch_last_used(self, api_key_id: UUID) -> None:
        stmt = (
            update(ApiKeyModel).where(ApiKeyModel.id == api_key_id).values(last_used_at=func.now())
        )
        await self._s.execute(stmt)

    async def revoke(self, tenant_id: UUID, api_key_id: UUID) -> bool:
        stmt = (
            update(ApiKeyModel)
            .where(
                ApiKeyModel.id == api_key_id,
                ApiKeyModel.tenant_id == tenant_id,
            )
            .values(is_active=False)
        )
        result = await self._s.execute(stmt)
        return cast("CursorResult[Any]", result).rowcount > 0


class SqlAlchemyDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, document: Document) -> Document:
        self._s.add(mp.document_to_model(document))
        await self._s.flush()
        return document

    async def get(self, tenant_id: UUID, document_id: UUID) -> Document | None:
        stmt = select(DocumentModel).where(
            DocumentModel.id == document_id,
            DocumentModel.tenant_id == tenant_id,
        )
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.document_to_entity(m) if m else None


class SqlAlchemyProcessingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, job: ProcessingJob) -> ProcessingJob:
        self._s.add(mp.job_to_model(job))
        await self._s.flush()
        return job

    async def get(self, tenant_id: UUID, job_id: UUID) -> ProcessingJob | None:
        stmt = select(ProcessingJobModel).where(
            ProcessingJobModel.id == job_id,
            ProcessingJobModel.tenant_id == tenant_id,
        )
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.job_to_entity(m) if m else None

    async def get_for_update(self, job_id: UUID) -> ProcessingJob | None:
        # SELECT ... FOR UPDATE: serializa entregas duplicadas do mesmo job.
        stmt = select(ProcessingJobModel).where(ProcessingJobModel.id == job_id).with_for_update()
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.job_to_entity(m) if m else None

    async def update(self, job: ProcessingJob) -> ProcessingJob:
        m = await self._s.get(ProcessingJobModel, job.id)
        if m is None:
            raise ValueError(f"job {job.id} inexistente para update")
        mp.apply_job_entity_to_model(job, m)
        await self._s.flush()
        return job

    async def find_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: str
    ) -> ProcessingJob | None:
        stmt = select(ProcessingJobModel).where(
            ProcessingJobModel.tenant_id == tenant_id,
            ProcessingJobModel.idempotency_key == idempotency_key,
        )
        m = (await self._s.execute(stmt)).scalar_one_or_none()
        return mp.job_to_entity(m) if m else None

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        *,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProcessingJob]:
        stmt = select(ProcessingJobModel).where(ProcessingJobModel.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(ProcessingJobModel.status == status.value)
        stmt = stmt.order_by(ProcessingJobModel.created_at.desc()).limit(limit).offset(offset)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [mp.job_to_entity(m) for m in rows]

    async def count_by_status(self, status: JobStatus) -> int:
        stmt = select(func.count()).where(ProcessingJobModel.status == status.value)
        return int((await self._s.execute(stmt)).scalar_one())


class SqlAlchemyWebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, endpoint: WebhookEndpoint) -> WebhookEndpoint:
        self._s.add(mp.webhook_to_model(endpoint))
        await self._s.flush()
        return endpoint

    async def list_by_tenant(self, tenant_id: UUID) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpointModel).where(WebhookEndpointModel.tenant_id == tenant_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [mp.webhook_to_entity(m) for m in rows]

    async def list_subscribers(
        self, tenant_id: UUID, event: WebhookEventType
    ) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpointModel).where(
            WebhookEndpointModel.tenant_id == tenant_id,
            WebhookEndpointModel.is_active.is_(True),
            WebhookEndpointModel.events.contains([event.value]),  # PG: events @> ARRAY[…]
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [mp.webhook_to_entity(m) for m in rows]

    async def delete(self, tenant_id: UUID, endpoint_id: UUID) -> bool:
        m = await self._s.get(WebhookEndpointModel, endpoint_id)
        if m is None or m.tenant_id != tenant_id:
            return False
        await self._s.delete(m)
        await self._s.flush()
        return True
