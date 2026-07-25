"""Tarefas Celery — a ponte entre o broker e os casos de uso (assíncronos).

Cada processo-filho do worker mantém UM event loop persistente e UM Container.
Reusar o mesmo loop evita o erro clássico "future attached to a different loop"
ao combinar Celery (prefork) com SQLAlchemy/redis assíncronos.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Coroutine
from typing import Any, TypeVar
from uuid import UUID

import structlog
from celery.signals import worker_process_init, worker_process_shutdown

from nexusdata.application.services.processing_service import (
    RetryableProcessingError,
)
from nexusdata.infrastructure.config import get_settings
from nexusdata.infrastructure.container import Container
from nexusdata.infrastructure.messaging.task_names import (
    TASK_DELIVER_WEBHOOK,
    TASK_PROCESS_DOCUMENT,
)
from nexusdata.infrastructure.observability.logging import configure_logging
from nexusdata.infrastructure.observability.metrics import record_webhook_delivery
from nexusdata.infrastructure.webhooks import WebhookDeliveryError
from nexusdata.worker.celery_app import celery_app

_log = structlog.get_logger(__name__)
T = TypeVar("T")

# Estado por processo-filho (preenchido em worker_process_init).
_loop: asyncio.AbstractEventLoop | None = None
_container: Container | None = None


@worker_process_init.connect
def _init_worker_process(**_: object) -> None:
    global _loop, _container
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.environment != "local")
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _container = Container(settings)
    _log.info("worker.process_initialized")


@worker_process_shutdown.connect
def _shutdown_worker_process(**_: object) -> None:
    global _loop, _container
    if _container is not None and _loop is not None:
        _loop.run_until_complete(_container.aclose())
        _loop.close()
    _loop = None
    _container = None


def _run(coro: Coroutine[Any, Any, T]) -> T:
    if _loop is None:
        raise RuntimeError("event loop do worker não inicializado")
    return _loop.run_until_complete(coro)


def _backoff_seconds(retries: int) -> int:
    """Backoff exponencial com teto e jitter (evita 'thundering herd')."""
    base = min(2**retries, 60)
    return int(base + random.uniform(0, base * 0.25))  # noqa: S311 - jitter, não cripto


@celery_app.task(bind=True, name=TASK_PROCESS_DOCUMENT, max_retries=10)
def process_document(self: Any, job_id: str, tenant_id: str) -> None:
    assert _container is not None
    try:
        _run(_container.processing_service.process(UUID(job_id)))
    except RetryableProcessingError as exc:
        countdown = _backoff_seconds(self.request.retries)
        _log.warning("task.retry", job_id=job_id, countdown=countdown, reason=exc.reason)
        raise self.retry(exc=exc, countdown=countdown) from exc


@celery_app.task(bind=True, name=TASK_DELIVER_WEBHOOK)
def deliver_webhook(self: Any, tenant_id: str, event: str, job_id: str) -> None:
    assert _container is not None
    settings = get_settings()
    try:
        _run(
            _container.webhook_dispatcher.deliver(
                tenant_id=UUID(tenant_id), event=event, job_id=UUID(job_id)
            )
        )
        record_webhook_delivery("success")
    except WebhookDeliveryError as exc:
        record_webhook_delivery("retry")
        if self.request.retries >= settings.webhook_max_retries:
            record_webhook_delivery("exhausted")
            _log.error("webhook.retries_exhausted", job_id=job_id, event=event)
            return
        raise self.retry(exc=exc, countdown=_backoff_seconds(self.request.retries)) from exc
