"""Processador mock determinístico.

Simula extração/validação de forma reprodutível (essencial para testes). O
resultado depende apenas do conteúdo do documento — mesma entrada, mesma saída.

Gatilhos de teste embutidos no `raw_payload` (úteis para exercitar retry/falha
e para o dashboard demonstrar os fluxos de erro):
    {"__force_error": true}        -> ProcessorError (transitório, dispara retry)
    {"__force_unavailable": true}  -> ProcessorUnavailableError (provider caiu)
"""

from __future__ import annotations

import hashlib

from nexusdata.application.ports.processor import (
    DocumentProcessor,
    ProcessingResult,
    ProcessorError,
    ProcessorUnavailableError,
)
from nexusdata.domain.entities import Document
from nexusdata.domain.value_objects.enums import DocumentType

_PROVIDER = "mock"


class MockDocumentProcessor(DocumentProcessor):
    async def process(self, document: Document) -> ProcessingResult:
        payload = document.raw_payload or {}
        if payload.get("__force_unavailable"):
            raise ProcessorUnavailableError("provider indisponível (simulado)")
        if payload.get("__force_error"):
            raise ProcessorError("falha transitória no processamento (simulada)")

        extracted = self._extract(document)
        # Confiança determinística derivada do checksum/identidade do documento.
        seed = document.checksum_sha256 or document.id.hex
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        confidence = round(0.80 + (int(digest[:2], 16) / 255) * 0.199, 4)

        warnings: tuple[str, ...] = ()
        if not extracted:
            warnings = ("nenhum campo estruturado reconhecido",)

        return ProcessingResult(
            extracted=extracted,
            confidence=confidence,
            provider=_PROVIDER,
            model="deterministic-v1",
            warnings=warnings,
        )

    @staticmethod
    def _extract(document: Document) -> dict[str, object]:
        payload = document.raw_payload or {}
        common: dict[str, object] = {
            "document_type": document.doc_type.value,
            "source_filename": document.filename,
            "field_count": len([k for k in payload if not k.startswith("__")]),
        }
        if document.doc_type is DocumentType.INVOICE:
            common |= {
                "invoice_number": payload.get("invoice_number", "UNKNOWN"),
                "total_amount": payload.get("total_amount", 0),
                "currency": payload.get("currency", "BRL"),
            }
        elif document.doc_type is DocumentType.CONTRACT:
            common |= {
                "parties": payload.get("parties", []),
                "effective_date": payload.get("effective_date"),
            }
        elif document.doc_type is DocumentType.SUPPORT_TICKET:
            text = str(payload.get("message", ""))
            common |= {
                "sentiment": "negative" if "problema" in text.lower() else "neutral",
                "priority": payload.get("priority", "normal"),
            }
        return common
