"""Tratamento centralizado de erros — respostas SEGURAS (nunca vazam interno).

Cada erro de domínio mapeia para um status HTTP e uma mensagem controlada.
Exceções inesperadas viram 500 genérico; o detalhe real vai só para o log
(com correlation_id), nunca para o cliente.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from nexusdata.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusinessRuleViolationError,
    DomainError,
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    RateLimitExceededError,
    TenantIsolationError,
)
from nexusdata.infrastructure.observability.logging import get_correlation_id

_log = structlog.get_logger(__name__)

_STATUS_MAP: dict[type[DomainError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    TenantIsolationError: status.HTTP_403_FORBIDDEN,
    AuthorizationError: status.HTTP_403_FORBIDDEN,
    EntityNotFoundError: status.HTTP_404_NOT_FOUND,
    DuplicateEntityError: status.HTTP_409_CONFLICT,
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    BusinessRuleViolationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RateLimitExceededError: status.HTTP_429_TOO_MANY_REQUESTS,
}


def _envelope(code: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    cid = get_correlation_id()
    if cid:
        body["correlation_id"] = cid
    if extra:
        body["error"].update(extra)
    return body


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_handler(_req: Request, exc: DomainError) -> JSONResponse:
        http_status = _STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
        headers = {}
        if isinstance(exc, AuthenticationError):
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=http_status,
            content=_envelope(exc.code, exc.message),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # Normaliza os erros do Pydantic sem ecoar valores enviados (evita
        # refletir dados sensíveis do corpo de volta ao cliente).
        details = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "issue": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope(
                "validation_error", "dados de entrada inválidos", {"fields": details}
            ),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_handler(_req: Request, _exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope("conflict", "conflito de dados"),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_req: Request, exc: Exception) -> JSONResponse:
        # O detalhe real fica só no log. O cliente recebe mensagem genérica.
        _log.error("unhandled_exception", error=str(exc), exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "erro interno inesperado"),
        )
