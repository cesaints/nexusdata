"""Provedor do cliente Redis assíncrono."""

from __future__ import annotations

from redis.asyncio import Redis

from nexusdata.infrastructure.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=5,
        socket_keepalive=True,
        retry_on_timeout=True,
    )
