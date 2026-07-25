"""Popula um tenant + admin de exemplo (idempotente).

Uso: `uv run python -m scripts.seed`
"""

from __future__ import annotations

import asyncio

import structlog

from nexusdata.application.dto.auth import RegisterTenantCommand
from nexusdata.domain.exceptions import DuplicateEntityError
from nexusdata.infrastructure.config import get_settings
from nexusdata.infrastructure.container import Container
from nexusdata.infrastructure.observability.logging import configure_logging

_log = structlog.get_logger(__name__)

_DEMO = RegisterTenantCommand(
    tenant_name="Acme Corp",
    tenant_slug="acme",
    admin_email="admin@acme.com",
    admin_password="ChangeMe-Str0ng!",
)


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=False)
    container = Container(settings)
    try:
        result = await container.auth_service.register_tenant(_DEMO)
        _log.info(
            "seed.created",
            tenant_id=str(result.tenant_id),
            admin=_DEMO.admin_email,
            password=_DEMO.admin_password,
        )
    except DuplicateEntityError:
        _log.info("seed.already_exists", slug=_DEMO.tenant_slug)
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(_run())
