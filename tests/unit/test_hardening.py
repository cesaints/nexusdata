"""Testes de regressão dos fixes do red-team de segurança."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from nexusdata.application.services.processing_service import (
    DocumentProcessingService,
    RetryableProcessingError,
)
from nexusdata.domain.entities import Document, ProcessingJob
from nexusdata.domain.exceptions import AuthenticationError
from nexusdata.domain.value_objects.enums import JobStatus
from nexusdata.infrastructure.config import Settings
from nexusdata.infrastructure.webhooks.dispatcher import WebhookDispatcher
from nexusdata.presentation.api.middleware.rate_limit import RateLimitMiddleware
from nexusdata.presentation.api.websocket import WebSocketConnectionManager
from tests.conftest import admin_headers
from tests.fakes import (
    FakeClock,
    FakeDatabase,
    InMemoryUnitOfWorkFactory,
    RecordingNotifier,
    RecordingPublisher,
)

pytestmark = pytest.mark.unit


# ---- Fix B: rate-limit identity é sempre por IP (não confia em headers) ----
def _req(headers: list[tuple[bytes, bytes]], client_ip: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/v1/documents/process",
            "query_string": b"",
            "headers": headers,
            "client": (client_ip, 1234),
            "server": ("t", 80),
            "scheme": "http",
        }
    )


def test_rate_limit_identity_ignores_spoofable_headers() -> None:
    spoofed = _req([(b"x-api-key", b"nxk_victim.anything")], "9.9.9.9")
    bearer = _req([(b"authorization", b"Bearer forged")], "9.9.9.9")
    assert RateLimitMiddleware._identity(spoofed) == "ip:9.9.9.9"
    assert RateLimitMiddleware._identity(bearer) == "ip:9.9.9.9"


# ---- Fix E: corpo acima do limite → 413 (antes de auth/roteamento) ----
async def test_oversized_body_rejected(client: Any) -> None:
    huge = b"x" * (2_097_152 + 10)  # > 2 MiB
    resp = await client.post("/api/v1/documents/process", content=huge)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


# ---- Fix G: WebSocket respeita o cap por tenant ----
async def test_ws_manager_enforces_cap() -> None:
    class FakeWS:
        def __init__(self) -> None:
            self.closed: int | None = None

        async def accept(self) -> None: ...
        async def send_text(self, _: str) -> None: ...
        async def close(self, code: int) -> None:
            self.closed = code

    mgr = WebSocketConnectionManager(max_per_tenant=2)
    a, b, c = FakeWS(), FakeWS(), FakeWS()
    assert await mgr.connect("t", a) is True  # type: ignore[arg-type]
    assert await mgr.connect("t", b) is True  # type: ignore[arg-type]
    assert await mgr.connect("t", c) is False  # type: ignore[arg-type] # estourou
    assert c.closed == 1013
    assert mgr.connection_count == 2


# ---- Fix C: exceção genérica no processamento vira retry (job não trava) ----
async def test_generic_processor_error_routes_to_retry() -> None:
    db = FakeDatabase()
    tenant = uuid4()
    doc = Document(tenant_id=tenant, submitted_by=tenant)
    job = ProcessingJob(tenant_id=tenant, document_id=doc.id)
    db.documents[doc.id] = doc
    db.jobs[job.id] = job

    class BoomProcessor:
        async def process(self, _: Document) -> Any:
            raise RuntimeError("provider timeout inesperado")

    svc = DocumentProcessingService(
        uow_factory=InMemoryUnitOfWorkFactory(db),
        processor=BoomProcessor(),  # type: ignore[arg-type]
        publisher=RecordingPublisher(),
        notifier=RecordingNotifier(),
        clock=FakeClock(),
    )
    with pytest.raises(RetryableProcessingError):
        await svc.process(job.id)
    assert db.jobs[job.id].status is JobStatus.RETRYING


# ---- Fix D: entrega duplicada enquanto PROCESSING é no-op (sem erro) ----
async def test_duplicate_delivery_while_processing_is_noop() -> None:
    db = FakeDatabase()
    tenant = uuid4()
    job = ProcessingJob(tenant_id=tenant, document_id=uuid4(), status=JobStatus.PROCESSING)
    db.jobs[job.id] = job

    svc = DocumentProcessingService(
        uow_factory=InMemoryUnitOfWorkFactory(db),
        processor=object(),  # type: ignore[arg-type] # não deve ser chamado
        publisher=RecordingPublisher(),
        notifier=RecordingNotifier(),
        clock=FakeClock(),
    )
    await svc.process(job.id)  # não levanta InvalidStateTransition
    assert db.jobs[job.id].status is JobStatus.PROCESSING


# ---- Fix H: tenant desativado revoga suas API keys ----
async def test_inactive_tenant_revokes_api_key(client: Any, container: Any) -> None:
    reg = await admin_headers(client)
    created = await client.post(
        "/api/v1/api-keys", headers=reg, json={"name": "k", "scopes": ["jobs:read"]}
    )
    full_key = created.json()["full_key"]
    # A chave funciona...
    ok = await client.get("/api/v1/jobs", headers={"X-API-Key": full_key})
    assert ok.status_code == 200
    # ...até o tenant ser desativado.
    for tenant in container.db.tenants.values():
        tenant.is_active = False
    blocked = await client.get("/api/v1/jobs", headers={"X-API-Key": full_key})
    assert blocked.status_code == 401


# ---- Fix A: pinning de IP monta a URL corretamente ----
def test_pin_url_rewrites_host_to_ip() -> None:
    assert (
        WebhookDispatcher._pin_url("https://hooks.acme.com/x", "203.0.113.5", 443)
        == "https://203.0.113.5:443/x"
    )
    assert "[2001:db8::1]" in WebhookDispatcher._pin_url("https://h/x", "2001:db8::1", 443)


# ---- Fix I: hardening de produção bloqueia segredos default ----
def test_production_rejects_default_db_password() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            jwt_secret_key=SecretStr("k" * 40),
            postgres_password=SecretStr("nexus_dev_password"),
            rabbitmq_password=SecretStr("strong-mq-secret"),
        )


def test_production_accepts_strong_secrets() -> None:
    cfg = Settings(
        environment="production",
        jwt_secret_key=SecretStr("k" * 40),
        postgres_password=SecretStr("strong-pg-secret"),
        rabbitmq_password=SecretStr("strong-mq-secret"),
    )
    assert cfg.is_production


def test_api_key_split_rejects_garbage() -> None:
    from nexusdata.infrastructure.security import ApiKeyServiceImpl

    with pytest.raises(AuthenticationError):
        ApiKeyServiceImpl().split("no-prefix-no-dot")
