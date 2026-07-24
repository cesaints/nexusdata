"""Logs estruturados (structlog) em JSON, com correlation_id propagado.

O `correlation_id` (Trace ID) é armazenado num ContextVar e injetado em todo
log da requisição — permite seguir uma requisição da API até o worker.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

import structlog

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def bind_correlation_id(correlation_id: str) -> None:
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def _add_correlation_id(
    _logger: Any, _name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    cid = _correlation_id.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        level=logging.getLevelNamesMapping().get(level.upper(), logging.INFO),
    )
