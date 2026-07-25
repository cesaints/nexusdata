# syntax=docker/dockerfile:1.7
# =============================================================================
# NexusData — imagem única para API e Worker (comando diferente no compose).
# Multi-stage: builder resolve deps com uv; runtime é slim e roda como não-root.
# =============================================================================

FROM python:3.14-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
# uv oficial (binário estático)
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

# --- Builder: instala dependências + projeto no /app/.venv ---
FROM base AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
# 1) Só o manifesto → cache de camada de dependências
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --all-extras --no-install-project
# 2) Código-fonte → instala o projeto
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --frozen --no-dev --all-extras

# --- Runtime: apenas o necessário ---
FROM base AS runtime
WORKDIR /app
RUN groupadd -r nexus && useradd -r -g nexus -d /app nexus
COPY --from=builder --chown=nexus:nexus /app /app
ENV PATH="/app/.venv/bin:${PATH}"
USER nexus
EXPOSE 8000

# Healthcheck da API (sobrescrito/ignorado no serviço de worker).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live').status==200 else 1)" || exit 1

CMD ["uvicorn", "nexusdata.main:app", "--host", "0.0.0.0", "--port", "8000"]
