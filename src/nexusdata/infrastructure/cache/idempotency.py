"""Idempotência em nível HTTP (Idempotency-Key) usando Redis.

Fluxo:
  1. `start()` reserva a chave atomicamente (SET NX). Primeira vez => NEW.
  2. Concorrência: outra requisição com a mesma chave em voo => IN_PROGRESS
     (o endpoint responde 409, evitando processamento duplo).
  3. Replay: se já houver resposta salva => REPLAY (retorna a resposta original).
  4. Abuso: mesma chave com corpo diferente => CONFLICT_FINGERPRINT (422).

Isso complementa a garantia de idempotência no banco (unique constraint do job).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum, auto
from uuid import UUID

from redis.asyncio import Redis


class IdempotencyOutcome(Enum):
    NEW = auto()
    IN_PROGRESS = auto()
    REPLAY = auto()
    CONFLICT_FINGERPRINT = auto()


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    status_code: int
    body: str


@dataclass(frozen=True, slots=True)
class IdempotencyLookup:
    outcome: IdempotencyOutcome
    record: IdempotencyRecord | None = None


class IdempotencyStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(tenant_id: UUID, key: str) -> str:
        return f"idem:{tenant_id}:{key}"

    async def start(
        self, *, tenant_id: UUID, key: str, fingerprint: str, ttl_seconds: int
    ) -> IdempotencyLookup:
        redis_key = self._key(tenant_id, key)
        placeholder = json.dumps({"state": "in_progress", "fp": fingerprint})

        was_set = await self._redis.set(redis_key, placeholder, nx=True, ex=ttl_seconds)
        if was_set:
            return IdempotencyLookup(IdempotencyOutcome.NEW)

        raw = await self._redis.get(redis_key)
        if raw is None:
            # Expirou entre SET e GET: tenta reservar mais uma vez.
            was_set = await self._redis.set(redis_key, placeholder, nx=True, ex=ttl_seconds)
            if was_set:
                return IdempotencyLookup(IdempotencyOutcome.NEW)
            raw = await self._redis.get(redis_key)
            if raw is None:
                return IdempotencyLookup(IdempotencyOutcome.NEW)

        data = json.loads(raw)
        if data.get("fp") != fingerprint:
            return IdempotencyLookup(IdempotencyOutcome.CONFLICT_FINGERPRINT)
        if data.get("state") == "completed":
            return IdempotencyLookup(
                IdempotencyOutcome.REPLAY,
                IdempotencyRecord(status_code=int(data["status_code"]), body=str(data["body"])),
            )
        return IdempotencyLookup(IdempotencyOutcome.IN_PROGRESS)

    async def finish(
        self,
        *,
        tenant_id: UUID,
        key: str,
        fingerprint: str,
        record: IdempotencyRecord,
        ttl_seconds: int,
    ) -> None:
        payload = json.dumps(
            {
                "state": "completed",
                "fp": fingerprint,
                "status_code": record.status_code,
                "body": record.body,
            }
        )
        await self._redis.set(self._key(tenant_id, key), payload, ex=ttl_seconds)

    async def release(self, *, tenant_id: UUID, key: str) -> None:
        """Libera a reserva se o processamento falhou (permite retry legítimo)."""
        await self._redis.delete(self._key(tenant_id, key))
