"""Middlewares de correlação, cabeçalhos de segurança e métricas."""

from __future__ import annotations

import re
import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from nexusdata.infrastructure.observability.logging import bind_correlation_id
from nexusdata.infrastructure.observability.metrics import observe_http_request

_CID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Garante um correlation_id por requisição (aceita do cliente se válido)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
        cid = incoming if incoming and _CID_RE.match(incoming) else uuid4().hex
        bind_correlation_id(cid)
        structlog.contextvars.bind_contextvars(correlation_id=cid)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Correlation-ID"] = cid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeçalhos de segurança padrão para respostas da API."""

    def __init__(self, app: object, *, hsts: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # CSP estrita para JSON da API; a doc interativa (/docs, /redoc) precisa
        # carregar scripts/estilos, então recebe apenas o cabeçalho anti-clickjacking.
        is_docs = request.url.path.startswith(("/docs", "/redoc"))
        if not is_docs:
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        if "server" in response.headers:
            del response.headers["server"]
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Mede latência/contagem por rota (usa o template da rota, não a URL crua,
    para não explodir a cardinalidade das métricas)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        route = request.scope.get("route")
        path = getattr(route, "path", None) or "unmatched"
        observe_http_request(
            method=request.method,
            path=path,
            status=response.status_code,
            duration_seconds=duration,
        )
        return response
