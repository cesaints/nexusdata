"""Testes do store de idempotência HTTP (sobre fakeredis)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fakeredis import FakeAsyncRedis

from nexusdata.infrastructure.cache.idempotency import (
    IdempotencyOutcome,
    IdempotencyRecord,
    IdempotencyStore,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def store() -> IdempotencyStore:
    return IdempotencyStore(FakeAsyncRedis(decode_responses=True))


async def test_new_then_in_progress_then_replay(store: IdempotencyStore) -> None:
    tenant = uuid4()
    key, fp = "abc", "fp1"

    first = await store.start(tenant_id=tenant, key=key, fingerprint=fp, ttl_seconds=60)
    assert first.outcome is IdempotencyOutcome.NEW

    second = await store.start(tenant_id=tenant, key=key, fingerprint=fp, ttl_seconds=60)
    assert second.outcome is IdempotencyOutcome.IN_PROGRESS

    await store.finish(
        tenant_id=tenant,
        key=key,
        fingerprint=fp,
        record=IdempotencyRecord(status_code=202, body='{"job":"1"}'),
        ttl_seconds=60,
    )
    third = await store.start(tenant_id=tenant, key=key, fingerprint=fp, ttl_seconds=60)
    assert third.outcome is IdempotencyOutcome.REPLAY
    assert third.record is not None
    assert third.record.status_code == 202


async def test_fingerprint_conflict(store: IdempotencyStore) -> None:
    tenant = uuid4()
    await store.start(tenant_id=tenant, key="k", fingerprint="fpA", ttl_seconds=60)
    clash = await store.start(tenant_id=tenant, key="k", fingerprint="fpB", ttl_seconds=60)
    assert clash.outcome is IdempotencyOutcome.CONFLICT_FINGERPRINT


async def test_release_allows_retry(store: IdempotencyStore) -> None:
    tenant = uuid4()
    await store.start(tenant_id=tenant, key="k", fingerprint="fp", ttl_seconds=60)
    await store.release(tenant_id=tenant, key="k")
    again = await store.start(tenant_id=tenant, key="k", fingerprint="fp", ttl_seconds=60)
    assert again.outcome is IdempotencyOutcome.NEW
