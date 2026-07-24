"""Circuit Breaker assíncrono.

Protege o sistema de um provider externo instável: após N falhas consecutivas,
o circuito ABRE e as chamadas passam a falhar rápido (sem esperar timeout),
dando tempo para o provider se recuperar. Depois de um período, entra em
HALF_OPEN para testar com uma chamada; sucesso fecha, falha reabre.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

from nexusdata.application.ports.processor import ProcessorUnavailableError

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AsyncCircuitBreaker:
    def __init__(
        self,
        *,
        fail_threshold: int = 5,
        reset_timeout_seconds: float = 30.0,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fail_threshold = fail_threshold
        self._reset_timeout = reset_timeout_seconds
        self._now = time_source
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        if self._state is CircuitState.OPEN:
            if self._now() - self._opened_at >= self._reset_timeout:
                self._state = CircuitState.HALF_OPEN
            else:
                raise ProcessorUnavailableError("circuito aberto: provider instável")

        try:
            result = await func()
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _on_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        self._failures += 1
        if self._state is CircuitState.HALF_OPEN or self._failures >= self._fail_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._now()
