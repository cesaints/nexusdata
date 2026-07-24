"""Testes dos casos de uso de processamento e isolamento de tenant."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from nexusdata.application.dto.common import AuthContext, AuthMethod
from nexusdata.application.dto.documents import IngestDocumentCommand
from nexusdata.application.services.processing_service import (
    RetryableProcessingError,
)
from nexusdata.domain.exceptions import EntityNotFoundError, TenantIsolationError
from nexusdata.domain.value_objects.enums import JobStatus, Role

pytestmark = pytest.mark.unit


def _auth(tenant_id: Any, user_id: Any) -> AuthContext:
    return AuthContext(
        user_id=user_id, tenant_id=tenant_id, role=Role.ADMIN, method=AuthMethod.JWT
    )


async def _ingest(container: Any, *, payload: dict[str, object] | None = None) -> Any:
    tenant, user = uuid4(), uuid4()
    auth = _auth(tenant, user)
    cmd = IngestDocumentCommand(
        tenant_id=tenant, submitted_by=user, raw_payload=payload
    )
    result = await container.document_service.ingest(cmd, auth=auth)
    return tenant, user, result


async def test_ingest_publishes_and_creates_pending(container: Any) -> None:
    _, _, result = await _ingest(container)
    assert result.status is JobStatus.PENDING
    assert len(container.publisher.jobs) == 1


async def test_processing_happy_path(container: Any) -> None:
    _, _, result = await _ingest(container, payload={"invoice_number": "NF-9"})
    await container.processing_service.process(result.job_id)

    job = container.db.jobs[result.job_id]
    assert job.status is JobStatus.COMPLETED
    assert job.result is not None
    # Notificou processing + completed; disparou webhook job.completed.
    statuses = [s for _, s in container.notifier.updates]
    assert "processing" in statuses and "completed" in statuses
    assert any(ev == "job.completed" for _, ev, _ in container.publisher.webhook_events)


async def test_processing_transient_error_schedules_retry(container: Any) -> None:
    _, _, result = await _ingest(container, payload={"__force_error": True})
    with pytest.raises(RetryableProcessingError):
        await container.processing_service.process(result.job_id)
    assert container.db.jobs[result.job_id].status is JobStatus.RETRYING


async def test_processing_exhausts_and_fails(container: Any) -> None:
    _, _, result = await _ingest(container, payload={"__force_error": True})
    container.db.jobs[result.job_id].max_attempts = 1  # sem retries
    await container.processing_service.process(result.job_id)

    job = container.db.jobs[result.job_id]
    assert job.status is JobStatus.FAILED
    assert any(ev == "job.failed" for _, ev, _ in container.publisher.webhook_events)


async def test_idempotent_ingest_returns_same_job(container: Any) -> None:
    tenant, user = uuid4(), uuid4()
    auth = _auth(tenant, user)
    cmd = IngestDocumentCommand(
        tenant_id=tenant, submitted_by=user, idempotency_key="dup-key"
    )
    first = await container.document_service.ingest(cmd, auth=auth)
    second = await container.document_service.ingest(cmd, auth=auth)
    assert first.job_id == second.job_id
    assert second.idempotent_replay is True


async def test_tenant_isolation_on_job_read(container: Any) -> None:
    tenant_a, user_a, result = await _ingest(container)
    attacker = _auth(uuid4(), uuid4())  # outro tenant
    with pytest.raises(EntityNotFoundError):
        await container.job_service.get(result.job_id, auth=attacker)


async def test_ingest_rejects_tenant_spoofing(container: Any) -> None:
    auth = _auth(uuid4(), uuid4())
    cmd = IngestDocumentCommand(tenant_id=uuid4(), submitted_by=uuid4())  # tenant divergente
    with pytest.raises(TenantIsolationError):
        await container.document_service.ingest(cmd, auth=auth)
