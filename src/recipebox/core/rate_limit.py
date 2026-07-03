"""Per-user token-bucket rate limiter.

Lua script is the standard pattern: the read-modify-write of bucket state must be
atomic across concurrent requests, and Redis runs Lua scripts single-threaded
server-side. No race condition possible — even under high concurrency, the bucket
can never be over-spent.

Algorithm per request:
  1. Read current tokens + last refill time
  2. Refill: tokens = min(capacity, tokens + elapsed * refill_rate)
  3. If tokens >= 1, deduct 1, write back, return ALLOW
  4. Else, return DENY
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import redis.asyncio as aioredis

_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last')
local tokens = tonumber(data[1])
local last = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last = now
end

local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens < 1 then
    redis.call('HSET', key, 'tokens', tokens, 'last', now)
    redis.call('EXPIRE', key, 3600)
    return 0
end

tokens = tokens - 1
redis.call('HSET', key, 'tokens', tokens, 'last', now)
redis.call('EXPIRE', key, 3600)
return 1
"""


class RateLimiter(ABC):
    @abstractmethod
    async def allow(self, user_key: str) -> bool: ...


class RedisTokenBucket(RateLimiter):
    """capacity = max burst; refill_rate = sustained req/sec."""

    def __init__(self, client: aioredis.Redis, capacity: int, refill_rate_per_sec: float) -> None:
        self._client = client
        self._capacity = capacity
        self._rate = refill_rate_per_sec
        self._script = client.register_script(_TOKEN_BUCKET_LUA)

    async def allow(self, user_key: str) -> bool:
        key = f"rate:agent:{user_key}"
        result = await self._script(keys=[key], args=[self._capacity, self._rate, time.time()])
        return bool(result)


class InMemoryRateLimiter(RateLimiter):
    """Test double — same algorithm but using Python state."""

    def __init__(self, capacity: int, refill_rate_per_sec: float) -> None:
        self._capacity = capacity
        self._rate = refill_rate_per_sec
        self._buckets: dict[str, tuple[float, float]] = {}  # user → (tokens, last)

    async def allow(self, user_key: str) -> bool:
        now = time.time()
        tokens, last = self._buckets.get(user_key, (self._capacity, now))
        tokens = min(self._capacity, tokens + max(0.0, now - last) * self._rate)
        if tokens < 1:
            self._buckets[user_key] = (tokens, now)
            return False
        self._buckets[user_key] = (tokens - 1, now)
        return True


class AlwaysAllow(RateLimiter):
    """Used when Redis isn't configured (CI, tests that don't care)."""

    async def allow(self, user_key: str) -> bool:
        return True
