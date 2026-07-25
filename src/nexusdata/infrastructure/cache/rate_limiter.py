"""Rate limiter distribuído (janela fixa atômica no Redis).

A atomicidade INCR+EXPIRE é garantida por um script Lua — evita a corrida
clássica em que a chave fica sem TTL (e o limite "gruda" para sempre).
"Fail-open" controlado: se o Redis cair, o middlewaredecide a política.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

# KEYS[1]=chave  ARGV[1]=ttl_ms  ->  retorna a contagem atual da janela.
_FIXED_WINDOW_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return current
"""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def check(self, *, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        redis_key = f"ratelimit:{key}"
        count = int(
            await self._redis.eval(_FIXED_WINDOW_LUA, 1, redis_key, str(window_seconds * 1000))
        )
        if count > limit:
            ttl_ms = int(await self._redis.pttl(redis_key))
            retry_after = max(1, (ttl_ms + 999) // 1000) if ttl_ms > 0 else window_seconds
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                retry_after_seconds=retry_after,
            )
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=0,
        )
