"""Middleware de rate limiting distribuído (Redis).

Identidade do limite (em ordem de precedência):
  1. Prefixo da API key (X-API-Key)   — limite por integração.
  2. Fingerprint do JWT (hash)        — limite por sessão/usuário.
  3. IP do cliente                    — fallback anônimo.

Fail-open deliberado: se o Redis estiver indisponível, a requisição passa (e
logamos). Preferimos disponibilidade a bloquear tudo por uma falha de cache.
"""

from __future__ import annotations

import hashlib

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_log = structlog.get_logger(__name__)

_EXEMPT_PREFIXES = (
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        container = request.app.state.container
        settings = container.settings
        identity = self._identity(request)

        try:
            result = await container.rate_limiter.check(
                key=identity,
                limit=settings.rate_limit_requests,
                window_seconds=settings.rate_limit_window_seconds,
            )
        except Exception as exc:
            _log.warning("ratelimit.unavailable", error=str(exc))
            return await call_next(request)

        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "limite de requisições excedido",
                    }
                },
                headers={
                    "Retry-After": str(result.retry_after_seconds),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        return response

    @staticmethod
    def _identity(request: Request) -> str:
        api_key = request.headers.get("x-api-key")
        if api_key:
            prefix = api_key.split(".", 1)[0]
            return f"apikey:{prefix}"
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
            fp = hashlib.sha256(token.encode()).hexdigest()[:24]
            return f"jwt:{fp}"
        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"
