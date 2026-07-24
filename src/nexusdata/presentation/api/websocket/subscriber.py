"""Assinante Redis Pub/Sub que repassa updates de jobs aos WebSockets locais.

Roda como tarefa de fundo no processo da API. O worker publica; aqui recebemos
e distribuímos às conexões do tenant correspondente.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from redis.asyncio import Redis

from nexusdata.infrastructure.messaging.notifier import CHANNEL_PREFIX
from nexusdata.presentation.api.websocket.manager import WebSocketConnectionManager

_log = structlog.get_logger(__name__)


class JobUpdatesSubscriber:
    def __init__(self, *, redis: Redis, manager: WebSocketConnectionManager) -> None:
        self._redis = redis
        self._manager = manager
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="ws-job-subscriber")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{CHANNEL_PREFIX}:*")
        _log.info("ws.subscriber_started", pattern=f"{CHANNEL_PREFIX}:*")
        try:
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                channel = str(message["channel"])
                tenant_id = channel.rsplit(":", 1)[-1]
                await self._manager.broadcast(tenant_id, str(message["data"]))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.error("ws.subscriber_error", error=str(exc))
        finally:
            await pubsub.aclose()  # type: ignore[no-untyped-call]
