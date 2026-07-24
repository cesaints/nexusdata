"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

from nexusdata.infrastructure.config import Settings
from nexusdata.presentation.api.app import create_app
from nexusdata.presentation.api.websocket import WebSocketConnectionManager
from tests.fakes import build_test_container


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="local",
        jwt_secret_key=SecretStr("test-secret-" + "a" * 40),
        access_token_expire_minutes=15,
        rate_limit_requests=1000,
    )


@pytest.fixture
def container(settings: Settings) -> Any:
    return build_test_container(settings)


@pytest.fixture
def app(settings: Settings, container: Any) -> Iterator[Any]:
    application = create_app(settings)
    application.state.container = container
    application.state.ws_manager = WebSocketConnectionManager()
    yield application


@pytest_asyncio.fixture
async def client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        yield ac


async def register_tenant(
    client: httpx.AsyncClient,
    *,
    slug: str = "acme",
    email: str = "admin@acme.com",
    password: str = "Sup3rStr0ngPass!",
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Acme",
            "tenant_slug": slug,
            "admin_email": email,
            "admin_password": password,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def login(
    client: httpx.AsyncClient,
    *,
    email: str = "admin@acme.com",
    password: str = "Sup3rStr0ngPass!",
) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def admin_headers(client: httpx.AsyncClient, **kw: Any) -> dict[str, str]:
    await register_tenant(client, **kw)
    token = await login(
        client,
        email=kw.get("email", "admin@acme.com"),
        password=kw.get("password", "Sup3rStr0ngPass!"),
    )
    return {"Authorization": f"Bearer {token}"}
