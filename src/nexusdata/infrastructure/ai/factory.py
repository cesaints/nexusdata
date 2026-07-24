"""Fábrica que monta o DocumentProcessor conforme a configuração."""

from __future__ import annotations

from nexusdata.application.ports.processor import DocumentProcessor
from nexusdata.infrastructure.ai.circuit_breaker import AsyncCircuitBreaker
from nexusdata.infrastructure.ai.mock_processor import MockDocumentProcessor
from nexusdata.infrastructure.ai.resilient_processor import ResilientProcessor
from nexusdata.infrastructure.config import Settings


def build_processor(settings: Settings) -> DocumentProcessor:
    breaker = AsyncCircuitBreaker(
        fail_threshold=settings.circuit_breaker_fail_threshold,
        reset_timeout_seconds=settings.circuit_breaker_reset_seconds,
    )

    inner: DocumentProcessor
    if settings.ai_provider == "mock":
        inner = MockDocumentProcessor()
    else:
        # Ponto de extensão: implementar ClaudeProcessor/OpenAIProcessor lendo
        # settings.ai_api_key. Mantém o resto do sistema inalterado (mesmo port).
        raise NotImplementedError(
            f"provider de IA '{settings.ai_provider}' ainda não implementado; "
            "use NEXUS_AI_PROVIDER=mock ou implemente o adapter correspondente"
        )

    return ResilientProcessor(inner, breaker=breaker, max_retries=settings.ai_max_retries)
