"""Port do processador de documentos (camada de IA plugável).

O caso de uso de processamento depende APENAS desta interface. A troca entre
mock determinístico, Claude, OpenAI ou um pipeline OCR+regras acontece na
infraestrutura, sem tocar na regra de negócio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from nexusdata.domain.entities import Document


class ProcessorError(Exception):
    """Falha ao processar — o worker decide retry vs. falha definitiva."""


class ProcessorUnavailableError(ProcessorError):
    """Provider externo indisponível (circuit breaker aberto / timeout)."""


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    """Saída estruturada da extração/validação de um documento."""

    extracted: dict[str, object]
    confidence: float
    provider: str
    model: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class DocumentProcessor(Protocol):
    async def process(self, document: Document) -> ProcessingResult: ...
