"""Testes de fluxo da API (ASGITransport, in-memory) — exercita rotas, deps,
middlewares, auth e handlers de erro de ponta a ponta."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest

from tests.conftest import admin_headers, register_tenant

pytestmark = pytest.mark.unit


async def test_health_live(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


async def test_register_and_duplicate(client: httpx.AsyncClient) -> None:
    await register_tenant(client)
    dup = await client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Acme2",
            "tenant_slug": "acme",
            "admin_email": "other@acme.com",
            "admin_password": "Sup3rStr0ngPass!",
        },
    )
    assert dup.status_code == 409


async def test_login_wrong_password(client: httpx.AsyncClient) -> None:
    await register_tenant(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@acme.com", "password": "errada"},
    )
    assert resp.status_code == 401


async def test_ingest_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/documents/process", json={"doc_type": "generic"})
    assert resp.status_code == 401


async def test_ingest_returns_202_and_job_visible(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    resp = await client.post(
        "/api/v1/documents/process",
        headers=headers,
        json={"doc_type": "invoice", "raw_payload": {"invoice_number": "NF-1"}},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    got = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["status"] == "pending"


async def test_ingest_idempotency_replay(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    body = {"doc_type": "generic", "raw_payload": {"x": 1}}
    h = {**headers, "Idempotency-Key": "req-123"}

    first = await client.post("/api/v1/documents/process", headers=h, json=body)
    second = await client.post("/api/v1/documents/process", headers=h, json=body)
    assert first.status_code == 202
    assert second.headers.get("Idempotent-Replay") == "true"
    assert first.json()["job_id"] == second.json()["job_id"]


async def test_idempotency_key_reuse_conflict(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    h = {**headers, "Idempotency-Key": "same-key"}
    await client.post("/api/v1/documents/process", headers=h, json={"doc_type": "generic"})
    clash = await client.post("/api/v1/documents/process", headers=h, json={"doc_type": "invoice"})
    assert clash.status_code == 422
    assert clash.json()["error"]["code"] == "idempotency_key_reuse"


async def test_completed_job_flow(client: httpx.AsyncClient, container: Any) -> None:
    headers = await admin_headers(client)
    resp = await client.post(
        "/api/v1/documents/process",
        headers=headers,
        json={"doc_type": "invoice", "raw_payload": {"invoice_number": "NF-42"}},
    )
    job_id = resp.json()["job_id"]
    await container.processing_service.process(UUID(job_id))

    got = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert got.json()["status"] == "completed"
    assert got.json()["result"]["extracted"]["invoice_number"] == "NF-42"


async def test_api_key_lifecycle_and_scope(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    created = await client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"name": "ci", "scopes": ["documents:write", "jobs:read"]},
    )
    assert created.status_code == 201
    full_key = created.json()["full_key"]

    # A API key ingere documentos (escopo documents:write).
    ing = await client.post(
        "/api/v1/documents/process",
        headers={"X-API-Key": full_key},
        json={"doc_type": "generic"},
    )
    assert ing.status_code == 202

    # Mas NÃO pode gerenciar api-keys (requer admin via JWT).
    forbidden = await client.post(
        "/api/v1/api-keys",
        headers={"X-API-Key": full_key},
        json={"name": "x", "scopes": ["jobs:read"]},
    )
    assert forbidden.status_code == 403


async def test_webhook_requires_https(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    insecure = await client.post(
        "/api/v1/webhooks",
        headers=headers,
        json={"url": "http://evil.test/hook", "events": ["job.completed"]},
    )
    assert insecure.status_code == 422

    secure = await client.post(
        "/api/v1/webhooks",
        headers=headers,
        json={"url": "https://client.test/hook", "events": ["job.completed"]},
    )
    assert secure.status_code == 201
    assert "secret" in secure.json()


async def test_unknown_job_is_404(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    resp = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404


async def test_rejects_unknown_fields(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    resp = await client.post(
        "/api/v1/documents/process",
        headers=headers,
        json={"doc_type": "generic", "tenant_id": "hack", "role": "admin"},
    )
    assert resp.status_code == 422


async def test_security_headers_present(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "X-Correlation-ID" in resp.headers


async def test_readiness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"


async def test_metrics_endpoint(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    await client.post("/api/v1/documents/process", headers=headers, json={"doc_type": "generic"})
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert b"nexus_jobs_pending" in resp.content


async def test_me_endpoint(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
    assert resp.json()["auth_method"] == "jwt"


async def test_refresh_flow(client: httpx.AsyncClient) -> None:
    await register_tenant(client)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@acme.com", "password": "Sup3rStr0ngPass!"},
    )
    refresh_token = login_resp.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_list_and_delete_api_key(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    created = await client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"name": "k", "scopes": ["jobs:read"]},
    )
    key_id = created.json()["id"]
    listing = await client.get("/api/v1/api-keys", headers=headers)
    assert any(k["id"] == key_id for k in listing.json())
    deleted = await client.delete(f"/api/v1/api-keys/{key_id}", headers=headers)
    assert deleted.status_code == 204


async def test_list_and_delete_webhook(client: httpx.AsyncClient) -> None:
    headers = await admin_headers(client)
    created = await client.post(
        "/api/v1/webhooks",
        headers=headers,
        json={"url": "https://client.test/hook", "events": ["job.completed"]},
    )
    wid = created.json()["id"]
    listing = await client.get("/api/v1/webhooks", headers=headers)
    assert any(w["id"] == wid for w in listing.json())
    deleted = await client.delete(f"/api/v1/webhooks/{wid}", headers=headers)
    assert deleted.status_code == 204
