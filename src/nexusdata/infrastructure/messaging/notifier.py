"""Notifier de tempo real via Redis Pub/Sub (implementa Notifier).

O worker publica atualizações num canal por tenant. O processo da API assina
esses canais e repassa aos WebSockets conectados. Isso desacopla worker (que
não tem as conexões WS) do processo que as mantém. É best-effort: uma falha de
notificação NUNCA quebra o processamento (a verdade está no banco/polling).
"""

from __future__ import annotations

import json

import structlog
from redis.asyncio import Redis

from nexusdata.domain.entities import ProcessingJob
from nexusdata.infrastructure.observability.metrics import record_job_processed

_log = structlog.get_logger(__name__)

CHANNEL_PREFIX = "nexus:jobs"


def channel_for(tenant_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{tenant_id}"


class RedisJobNotifier:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def notify_job_update(self, *, tenant_id: object, job: ProcessingJob) -> None:
        message = json.dumps(
            {
                "type": "job.update",
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "status": job.status.value,
                "attempts": job.attempts,
                "error": job.error,
                "has_result": job.result is not None,
            }
        )
        if job.is_terminal:
            record_job_processed(job.status.value)
        try:
            await self._redis.publish(channel_for(str(tenant_id)), message)
        except Exception as exc:
            _log.warning("notifier.publish_failed", error=str(exc), job_id=str(job.id))
