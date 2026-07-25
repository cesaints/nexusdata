"""Ponto de entrada ASGI da API (usado por `uvicorn nexusdata.main:app`)."""

from __future__ import annotations

from nexusdata.presentation.api.app import create_app

app = create_app()
