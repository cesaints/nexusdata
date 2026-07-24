"""Fábrica da aplicação FastAPI (composition da camada de apresentação)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexusdata import __version__
from nexusdata.infrastructure.config import Settings, get_settings
from nexusdata.infrastructure.container import Container
from nexusdata.infrastructure.observability.logging import configure_logging
from nexusdata.infrastructure.observability.tracing import setup_tracing
from nexusdata.presentation.api.errors import install_exception_handlers
from nexusdata.presentation.api.middleware import (
    CorrelationIdMiddleware,
    MetricsMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from nexusdata.presentation.api.v1.routers import (
    api_keys,
    auth,
    documents,
    jobs,
    webhooks,
)
from nexusdata.presentation.api.v1.routers import system as system_router
from nexusdata.presentation.api.websocket import (
    JobUpdatesSubscriber,
    WebSocketConnectionManager,
)
from nexusdata.presentation.api.websocket import routes as ws_routes


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.environment != "local")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container(settings)
        manager = WebSocketConnectionManager()
        subscriber = JobUpdatesSubscriber(redis=container.redis, manager=manager)

        app.state.container = container
        app.state.ws_manager = manager
        app.state.ws_subscriber = subscriber

        setup_tracing(settings, app=app, engine=container.engine)
        subscriber.start()
        try:
            yield
        finally:
            await subscriber.stop()
            await container.aclose()

    app = FastAPI(
        title="NexusData API",
        version=__version__,
        summary="Plataforma Multi-Tenant de Processamento Assíncrono e Inteligente (IDP)",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Middlewares — a ÚLTIMA chamada é a camada mais externa (roda primeiro).
    # Ordem externa->interna: CORS, Correlation, Security, RateLimit, Metrics.
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "Idempotency-Key"],
        expose_headers=[
            "X-Correlation-ID",
            "Idempotent-Replay",
            "Retry-After",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
        ],
        max_age=600,
    )

    install_exception_handlers(app)

    # Endpoints operacionais na raiz (fora do prefixo /api/v1).
    app.include_router(system_router.router)

    # API v1.
    api = APIRouter(prefix=settings.api_prefix)
    api.include_router(auth.router)
    api.include_router(documents.router)
    api.include_router(jobs.router)
    api.include_router(api_keys.router)
    api.include_router(webhooks.router)
    api.include_router(ws_routes.router)
    app.include_router(api)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "NexusData", "version": __version__, "docs": "/docs"}

    return app
