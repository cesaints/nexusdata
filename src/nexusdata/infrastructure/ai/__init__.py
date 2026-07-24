"""Camada de processamento/IA plugável."""

from nexusdata.infrastructure.ai.circuit_breaker import (
    AsyncCircuitBreaker,
    CircuitState,
)
from nexusdata.infrastructure.ai.factory import build_processor
from nexusdata.infrastructure.ai.mock_processor import MockDocumentProcessor
from nexusdata.infrastructure.ai.resilient_processor import ResilientProcessor

__all__ = [
    "AsyncCircuitBreaker",
    "CircuitState",
    "MockDocumentProcessor",
    "ResilientProcessor",
    "build_processor",
]
