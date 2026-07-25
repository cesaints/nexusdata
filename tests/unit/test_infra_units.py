"""Testes unitários de adapters de infraestrutura (sem Docker)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fakeredis import FakeAsyncRedis

from nexusdata.domain.entities import (
    ApiKey,
    Document,
    ProcessingJob,
    Tenant,
    User,
    WebhookEndpoint,
)
from nexusdata.domain.value_objects.enums import (
    ApiKeyScope,
    DocumentType,
    JobStatus,
    Role,
    WebhookEventType,
)
from nexusdata.infrastructure.cache.rate_limiter import RedisRateLimiter
from nexusdata.infrastructure.database import mappers as mp
from nexusdata.infrastructure.messaging.notifier import RedisJobNotifier
from nexusdata.infrastructure.messaging.publisher import CeleryEventPublisher
from nexusdata.presentation.api.websocket import WebSocketConnectionManager

pytestmark = pytest.mark.unit


# ---------------- Mappers (entidade ↔ model, sem DB) ----------------
def test_mappers_roundtrip() -> None:
    tid = uuid4()
    tenant = Tenant(name="Acme", slug="acme")
    assert mp.tenant_to_entity(mp.tenant_to_model(tenant)).slug == "acme"

    user = User(tenant_id=tid, email="a@b.com", password_hash="h", role=Role.ADMIN)
    assert mp.user_to_entity(mp.user_to_model(user)).role is Role.ADMIN

    key = ApiKey(
        tenant_id=tid,
        name="k",
        prefix="nxk_x",
        key_hash="h",
        scopes=frozenset({ApiKeyScope.JOBS_READ}),
    )
    assert ApiKeyScope.JOBS_READ in mp.api_key_to_entity(mp.api_key_to_model(key)).scopes

    doc = Document(tenant_id=tid, submitted_by=tid, doc_type=DocumentType.INVOICE)
    assert mp.document_to_entity(mp.document_to_model(doc)).doc_type is DocumentType.INVOICE

    job = ProcessingJob(tenant_id=tid, document_id=uuid4(), status=JobStatus.PROCESSING)
    assert mp.job_to_entity(mp.job_to_model(job)).status is JobStatus.PROCESSING

    wh = WebhookEndpoint(
        tenant_id=tid,
        url="https://x.test",
        secret="s",
        events=frozenset({WebhookEventType.JOB_COMPLETED}),
    )
    assert WebhookEventType.JOB_COMPLETED in mp.webhook_to_entity(mp.webhook_to_model(wh)).events


# ---------------- Publisher ----------------
def test_celery_publisher_sends_tasks() -> None:
    class FakeCelery:
        def __init__(self) -> None:
            self.sent: list[tuple[str, dict[str, Any], str]] = []

        def send_task(self, name: str, kwargs: dict[str, Any], queue: str) -> None:
            self.sent.append((name, kwargs, queue))

    celery = FakeCelery()
    pub = CeleryEventPublisher(celery)  # type: ignore[arg-type]
    pub.publish_document_job(job_id=uuid4(), tenant_id=uuid4())
    pub.publish_webhook_event(tenant_id=uuid4(), event="job.completed", job_id=uuid4())
    assert len(celery.sent) == 2


# ---------------- Notifier ----------------
async def test_notifier_publishes_and_counts_terminal() -> None:
    redis = FakeAsyncRedis(decode_responses=True)
    notifier = RedisJobNotifier(redis)
    tid = uuid4()
    job = ProcessingJob(tenant_id=tid, document_id=uuid4(), status=JobStatus.COMPLETED)
    await notifier.notify_job_update(tenant_id=tid, job=job)  # terminal
    job2 = ProcessingJob(tenant_id=tid, document_id=uuid4(), status=JobStatus.PROCESSING)
    await notifier.notify_job_update(tenant_id=tid, job=job2)  # não-terminal


# ---------------- Rate limiter ----------------
async def test_rate_limiter_blocks_over_limit() -> None:
    class StubRedis:
        def __init__(self) -> None:
            self.count = 0

        async def eval(self, *_: Any) -> int:
            self.count += 1
            return self.count

        async def pttl(self, _: str) -> int:
            return 5000

    limiter = RedisRateLimiter(StubRedis())  # type: ignore[arg-type]
    r1 = await limiter.check(key="u", limit=2, window_seconds=60)
    r2 = await limiter.check(key="u", limit=2, window_seconds=60)
    r3 = await limiter.check(key="u", limit=2, window_seconds=60)
    assert r1.allowed and r2.allowed
    assert not r3.allowed
    assert r3.retry_after_seconds == 5


# ---------------- WebSocket manager ----------------
async def test_ws_manager_broadcast_and_cleanup() -> None:
    class FakeWS:
        def __init__(self, *, fail: bool = False) -> None:
            self.sent: list[str] = []
            self.fail = fail
            self.accepted = False

        async def accept(self) -> None:
            self.accepted = True

        async def send_text(self, message: str) -> None:
            if self.fail:
                raise RuntimeError("conexão morta")
            self.sent.append(message)

    manager = WebSocketConnectionManager()
    good, bad = FakeWS(), FakeWS(fail=True)
    await manager.connect("t1", good)  # type: ignore[arg-type]
    await manager.connect("t1", bad)  # type: ignore[arg-type]
    assert manager.connection_count == 2

    await manager.broadcast("t1", "ola")
    assert good.sent == ["ola"]
    # A conexão morta foi removida automaticamente.
    assert manager.connection_count == 1

    await manager.disconnect("t1", good)  # type: ignore[arg-type]
    assert manager.connection_count == 0


# ---------------- Container (smoke, sem conectar) ----------------
async def test_container_wires_everything(settings: Any) -> None:
    from nexusdata.infrastructure.container import Container

    container = Container(settings)
    assert container.auth_service is not None
    assert container.processing_service is not None
    assert container.webhook_dispatcher is not None
    await container.aclose()


def test_import_main_builds_app() -> None:
    import nexusdata.main as m

    assert m.app is not None


def test_now_returns_utc() -> None:
    from nexusdata.infrastructure.clock import SystemClock

    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now <= datetime.now(UTC)


# ---------------- Anti-SSRF do dispatcher de webhooks ----------------
@pytest.mark.parametrize(
    "url",
    [
        "http://client.test/hook",  # não-HTTPS
        "https://127.0.0.1/hook",  # loopback
        "https://10.0.0.5/hook",  # privado
        "https://169.254.169.254/latest",  # metadata de nuvem
        "https://localhost/hook",  # resolve loopback
    ],
)
def test_webhook_ssrf_blocks_dangerous_urls(url: str) -> None:
    from nexusdata.infrastructure.webhooks.dispatcher import (
        WebhookDeliveryError,
        WebhookDispatcher,
    )

    with pytest.raises(WebhookDeliveryError):
        WebhookDispatcher._assert_public_url(url)


def test_webhook_ssrf_allows_public_ip() -> None:
    from nexusdata.infrastructure.webhooks.dispatcher import WebhookDispatcher

    # IP público literal (sem DNS): não deve levantar.
    WebhookDispatcher._assert_public_url("https://8.8.8.8/hook")
