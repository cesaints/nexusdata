"""Testes de integração da camada de banco (Postgres real via Testcontainers).

Validam as queries reais, o isolamento por tenant e as constraints (incl. a
unicidade de idempotência), coisas que fakes in-memory não provam.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from nexusdata.domain.entities import ApiKey, Document, ProcessingJob, Tenant, User
from nexusdata.domain.exceptions import DuplicateEntityError
from nexusdata.domain.value_objects.enums import ApiKeyScope, JobStatus, Role
from nexusdata.infrastructure.database.engine import create_session_factory
from nexusdata.infrastructure.database.models import Base
from nexusdata.infrastructure.database.unit_of_work import (
    SqlAlchemyUnitOfWorkFactory,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        raw = pg.get_connection_url()  # postgresql+psycopg2://...
        yield raw.replace("postgresql+psycopg2", "postgresql+asyncpg")


@pytest_asyncio.fixture
async def uow_factory(pg_url: str) -> AsyncIterator[SqlAlchemyUnitOfWorkFactory]:
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    yield factory
    await engine.dispose()


async def test_tenant_and_user_crud(uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid4().hex[:8]}")
    async with uow_factory() as uow:
        await uow.tenants.add(tenant)
        await uow.users.add(
            User(tenant_id=tenant.id, email=f"a-{uuid4().hex}@x.com", password_hash="h", role=Role.ADMIN)
        )
        await uow.commit()

    async with uow_factory() as uow:
        got = await uow.tenants.get_by_slug(tenant.slug)
        assert got is not None and got.id == tenant.id


async def test_idempotency_unique_constraint(
    uow_factory: SqlAlchemyUnitOfWorkFactory,
) -> None:
    tenant = Tenant(name="T", slug=f"t-{uuid4().hex[:8]}")
    doc = Document(tenant_id=tenant.id, submitted_by=uuid4())
    async with uow_factory() as uow:
        await uow.tenants.add(tenant)
        await uow.documents.add(doc)
        await uow.jobs.add(
            ProcessingJob(tenant_id=tenant.id, document_id=doc.id, idempotency_key="dup")
        )
        await uow.commit()

    # Segundo job com a MESMA idempotency_key → viola a unique parcial.
    with pytest.raises(DuplicateEntityError):
        async with uow_factory() as uow:
            await uow.jobs.add(
                ProcessingJob(tenant_id=tenant.id, document_id=doc.id, idempotency_key="dup")
            )
            await uow.commit()


async def test_tenant_isolation(uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
    t = Tenant(name="T", slug=f"t-{uuid4().hex[:8]}")
    doc = Document(tenant_id=t.id, submitted_by=uuid4())
    job = ProcessingJob(tenant_id=t.id, document_id=doc.id)
    async with uow_factory() as uow:
        await uow.tenants.add(t)
        await uow.documents.add(doc)
        await uow.jobs.add(job)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.jobs.get(t.id, job.id) is not None
        assert await uow.jobs.get(uuid4(), job.id) is None  # outro tenant → invisível


async def test_job_update_persists(uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
    from datetime import UTC, datetime

    t = Tenant(name="T", slug=f"t-{uuid4().hex[:8]}")
    doc = Document(tenant_id=t.id, submitted_by=uuid4())
    job = ProcessingJob(tenant_id=t.id, document_id=doc.id)
    async with uow_factory() as uow:
        await uow.tenants.add(t)
        await uow.documents.add(doc)
        await uow.jobs.add(job)
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.jobs.get_for_update(job.id)
        assert loaded is not None
        loaded.mark_processing(now=datetime.now(UTC))
        loaded.mark_completed(now=datetime.now(UTC), result={"ok": True})
        await uow.jobs.update(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        final = await uow.jobs.get(t.id, job.id)
        assert final is not None and final.status is JobStatus.COMPLETED


async def test_api_key_revoke(uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
    t = Tenant(name="T", slug=f"t-{uuid4().hex[:8]}")
    key = ApiKey(
        tenant_id=t.id, name="k", prefix=f"nxk_{uuid4().hex[:8]}", key_hash="h",
        scopes=frozenset({ApiKeyScope.JOBS_READ}),
    )
    async with uow_factory() as uow:
        await uow.tenants.add(t)
        await uow.api_keys.add(key)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.api_keys.revoke(t.id, key.id) is True
        await uow.commit()

    async with uow_factory() as uow:
        got = await uow.api_keys.get_by_prefix(key.prefix)
        assert got is not None and got.is_active is False
