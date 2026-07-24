"""Decorator de resiliência: Circuit Breaker + Retry com backoff exponencial.

Envolve qualquer `DocumentProcessor` (mock ou real). Falhas transitórias
(`ProcessorError`) são reprocessadas com backoff exponencial + jitter. Se o
provider estiver claramente fora (`ProcessorUnavailableError`), o circuito
abre e passa a falhar rápido — sem martelar o provider.
"""

from __future__ import annotations

import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from nexusdata.application.ports.processor import (
    DocumentProcessor,
    ProcessingResult,
    ProcessorError,
)
from nexusdata.domain.entities import Document
from nexusdata.infrastructure.ai.circuit_breaker import AsyncCircuitBreaker

_log = structlog.get_logger(__name__)


class ResilientProcessor(DocumentProcessor):
    def __init__(
        self,
        inner: DocumentProcessor,
        *,
        breaker: AsyncCircuitBreaker,
        max_retries: int,
    ) -> None:
        self._inner = inner
        self._breaker = breaker
        self._max_retries = max_retries

    async def process(self, document: Document) -> ProcessingResult:
        async def _guarded() -> ProcessingResult:
            return await self._breaker.call(lambda: self._inner.process(document))

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential_jitter(initial=0.5, max=8.0),
            retry=retry_if_exception_type(ProcessorError),
            reraise=True,
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    _log.warning(
                        "processor.retry",
                        document_id=str(document.id),
                        attempt=attempt.retry_state.attempt_number,
                    )
                return await _guarded()
        raise AssertionError("unreachable")  # pragma: no cover
