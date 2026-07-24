"""Tracing distribuído com OpenTelemetry (opcional, guardado por config).

Quando `NEXUS_OTEL_ENABLED=true`, instrumenta FastAPI e SQLAlchemy e exporta
spans via OTLP/HTTP. Desligado por padrão para não impor um coletor ao dev.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from nexusdata.infrastructure.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

_log = structlog.get_logger(__name__)


def setup_tracing(settings: Settings, *, app: FastAPI, engine: AsyncEngine) -> None:
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {"service.name": "nexusdata-api", "deployment.environment": settings.environment}
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
            )
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        _log.info("otel.enabled", endpoint=settings.otel_exporter_otlp_endpoint)
    except Exception as exc:
        _log.warning("otel.setup_failed", error=str(exc))
