"""Permite `python -m nexusdata` para subir a API via uvicorn."""

from __future__ import annotations

import uvicorn

from nexusdata.infrastructure.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "nexusdata.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "local",
        log_config=None,  # usamos structlog
    )


if __name__ == "__main__":
    main()
