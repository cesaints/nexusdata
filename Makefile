# =============================================================================
# NexusData — Makefile (atalhos de desenvolvimento)
# =============================================================================
.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help install hooks lint format typecheck test test-unit test-int cov \
        up down logs migrate revision seed run worker fmt check ci clean

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependências (uv sync) + extras dev
	uv sync --all-extras --group dev

hooks: ## Instala os git hooks (pre-commit)
	uv run pre-commit install --install-hooks

lint: ## Roda o linter (Ruff)
	uv run ruff check src tests

format: ## Formata o código (Ruff)
	uv run ruff format src tests

fmt: format ## alias de format

typecheck: ## Checagem de tipos estrita (Mypy)
	uv run mypy src

check: lint typecheck ## Lint + typecheck (rápido, pré-commit)

test-unit: ## Testes unitários (rápidos, mockados)
	uv run pytest -m unit

test-int: ## Testes de integração (Testcontainers)
	uv run pytest -m integration

test: ## Suíte completa + cobertura (>= 80%)
	uv run pytest

cov: test ## alias de test (com cobertura)

ci: check test ## Pipeline local equivalente ao CI

up: ## Sobe a stack local (Postgres, Redis, RabbitMQ, Qdrant, API, Worker)
	docker compose up -d --build

down: ## Derruba a stack local
	docker compose down -v

logs: ## Segue os logs da stack
	docker compose logs -f --tail=100

migrate: ## Aplica as migrations (alembic upgrade head)
	uv run alembic upgrade head

revision: ## Cria migration autogenerate. Uso: make revision m="mensagem"
	uv run alembic revision --autogenerate -m "$(m)"

seed: ## Popula dados iniciais (tenant + admin de exemplo)
	uv run python -m scripts.seed

run: ## Roda a API localmente (reload)
	uv run uvicorn nexusdata.presentation.api.app:create_app --factory --reload \
		--host 0.0.0.0 --port 8000

worker: ## Roda o worker Celery localmente
	uv run celery -A nexusdata.worker.celery_app.celery_app worker \
		--loglevel=info --concurrency=4

front: ## Roda o dashboard (Vite dev server)
	cd frontend && npm install && npm run dev

front-build: ## Builda o dashboard para produção
	cd frontend && npm install && npm run build

clean: ## Limpa caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
