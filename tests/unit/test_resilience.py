"""Testes de resiliência: Circuit Breaker, Retry e processador mock."""

from __future__ import annotations

from uuid import uuid4

import pytest

from nexusdata.application.ports.processor import (
    ProcessorError,
    ProcessorUnavailableError,
)
from nexusdata.domain.entities import Document
from nexusdata.domain.value_objects.enums import DocumentType
from nexusdata.infrastructure.ai import (
    AsyncCircuitBreaker,
    CircuitState,
    MockDocumentProcessor,
    ResilientProcessor,
)

pytestmark = pytest.mark.unit


def _doc(payload: dict[str, object] | None = None) -> Document:
    return Document(
        tenant_id=uuid4(),
        submitted_by=uuid4(),
        doc_type=DocumentType.INVOICE,
        raw_payload=payload,
    )


# ---------------- Circuit Breaker ----------------
async def test_circuit_opens_after_threshold() -> None:
    clock = {"t": 0.0}
    breaker = AsyncCircuitBreaker(
        fail_threshold=3, reset_timeout_seconds=10, time_source=lambda: clock["t"]
    )

    async def boom() -> None:
        raise ProcessorError("x")

    for _ in range(3):
        with pytest.raises(ProcessorError):
            await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    # Com o circuito aberto, falha rápido (sem chamar a função).
    with pytest.raises(ProcessorUnavailableError):
        await breaker.call(boom)


async def test_circuit_half_open_recovers() -> None:
    clock = {"t": 0.0}
    breaker = AsyncCircuitBreaker(
        fail_threshold=1, reset_timeout_seconds=5, time_source=lambda: clock["t"]
    )

    async def boom() -> None:
        raise ProcessorError("x")

    with pytest.raises(ProcessorError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    clock["t"] = 6.0  # passou o reset → HALF_OPEN na próxima chamada

    async def ok() -> str:
        return "ok"

    assert await breaker.call(ok) == "ok"
    assert breaker.state is CircuitState.CLOSED


# ---------------- Mock processor ----------------
async def test_mock_is_deterministic() -> None:
    proc = MockDocumentProcessor()
    doc = _doc({"invoice_number": "NF-1", "total_amount": 100})
    r1 = await proc.process(doc)
    r2 = await proc.process(doc)
    assert r1.confidence == r2.confidence
    assert r1.extracted["invoice_number"] == "NF-1"


async def test_mock_force_errors() -> None:
    proc = MockDocumentProcessor()
    with pytest.raises(ProcessorError):
        await proc.process(_doc({"__force_error": True}))
    with pytest.raises(ProcessorUnavailableError):
        await proc.process(_doc({"__force_unavailable": True}))


# ---------------- Resilient wrapper ----------------
async def test_resilient_retries_then_succeeds() -> None:
    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        async def process(self, document: Document) -> object:
            self.calls += 1
            if self.calls < 2:
                raise ProcessorError("transient")
            return await MockDocumentProcessor().process(document)

    breaker = AsyncCircuitBreaker(fail_threshold=10, reset_timeout_seconds=1)
    resilient = ResilientProcessor(Flaky(), breaker=breaker, max_retries=3)  # type: ignore[arg-type]
    result = await resilient.process(_doc({"invoice_number": "NF-2"}))
    assert result.extracted["invoice_number"] == "NF-2"


async def test_resilient_gives_up_after_max_retries() -> None:
    proc = MockDocumentProcessor()
    breaker = AsyncCircuitBreaker(fail_threshold=10, reset_timeout_seconds=1)
    resilient = ResilientProcessor(proc, breaker=breaker, max_retries=2)
    with pytest.raises(ProcessorError):
        await resilient.process(_doc({"__force_error": True}))
