"""Instância e configuração do Celery.

Escolhas de resiliência (nível sênior):
  * `task_acks_late=True` + `reject_on_worker_lost`: a mensagem só é confirmada
    após o processamento — se o worker morrer no meio, a mensagem volta à fila
    (at-least-once). O código de processamento é idempotente para tolerar isso.
  * `prefetch_multiplier=1`: distribuição justa para tarefas longas (um worker
    não açambarca a fila).
  * Serialização apenas JSON (nunca pickle) — evita RCE por desserialização.
"""

from __future__ import annotations

from celery import Celery

from nexusdata.infrastructure.config import get_settings
from nexusdata.infrastructure.messaging.task_names import (
    QUEUE_DOCUMENTS,
    QUEUE_WEBHOOKS,
    TASK_DELIVER_WEBHOOK,
    TASK_PROCESS_DOCUMENT,
)

_settings = get_settings()

celery_app = Celery(
    "nexusdata",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["nexusdata.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],  # NUNCA pickle
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,  # recicla processos (evita vazamentos)
    task_time_limit=300,
    task_soft_time_limit=270,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    task_default_queue=QUEUE_DOCUMENTS,
    task_routes={
        TASK_PROCESS_DOCUMENT: {"queue": QUEUE_DOCUMENTS},
        TASK_DELIVER_WEBHOOK: {"queue": QUEUE_WEBHOOKS},
    },
)
