import json

from httpx import AsyncClient

from recipebox.core.cache import CacheStats, CachingEmbedder, InMemoryCache
from recipebox.core.embeddings import Embedder
from recipebox.core.rate_limit import InMemoryRateLimiter
from tests.test_agent import StubAnthropic, _Block, _override_agent, _Response, auth, register_and_login

# ---- CachingEmbedder unit tests ----


class CountingEmbedder(Embedder):
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, text: str) -> list[float]:
        self.calls += 1
        return [float(len(text)), 0.0, 0.0]


class TestCachingEmbedder:
    async def test_first_call_misses_and_invokes_inner(self) -> None:
        inner = CountingEmbedder()
        cache = InMemoryCache()
        stats = CacheStats()
        embedder = CachingEmbedder(inner=inner, cache=cache, stats=stats)
        vec = await embedder.embed("hello")
        assert vec == [5.0, 0.0, 0.0]
        assert inner.calls == 1
        assert stats.hits == 0
        assert stats.misses == 1

    async def test_second_call_hits_cache(self) -> None:
        inner = CountingEmbedder()
        cache = InMemoryCache()
        stats = CacheStats()
        embedder = CachingEmbedder(inner=inner, cache=cache, stats=stats)
        await embedder.embed("hello")
        vec = await embedder.embed("hello")
        assert vec == [5.0, 0.0, 0.0]
        assert inner.calls == 1  # not called again
        assert stats.hits == 1
        assert stats.misses == 1

    async def test_different_text_misses_again(self) -> None:
        inner = CountingEmbedder()
        cache = InMemoryCache()
        stats = CacheStats()
        embedder = CachingEmbedder(inner=inner, cache=cache, stats=stats)
        await embedder.embed("hello")
        await embedder.embed("world")
        assert inner.calls == 2
        assert stats.misses == 2

    async def test_cache_value_is_json_decoded_back_to_floats(self) -> None:
        cache = InMemoryCache()
        stats = CacheStats()
        embedder = CachingEmbedder(inner=CountingEmbedder(), cache=cache, stats=stats)
        await embedder.embed("test")
        # Verify the cached value is JSON-serializable floats
        key = next(iter(cache._store))  # type: ignore[attr-defined]
        raw = cache._store[key]  # type: ignore[attr-defined]
        assert json.loads(raw.decode("utf-8")) == [4.0, 0.0, 0.0]


# ---- Rate limiter unit tests ----


class TestInMemoryRateLimiter:
    async def test_allows_up_to_capacity(self) -> None:
        # capacity=3, rate=0 (no refill within the test)
        limiter = InMemoryRateLimiter(capacity=3, refill_rate_per_sec=0.0)
        assert await limiter.allow("user1") is True
        assert await limiter.allow("user1") is True
        assert await limiter.allow("user1") is True
        assert await limiter.allow("user1") is False

    async def test_separate_users_have_separate_buckets(self) -> None:
        limiter = InMemoryRateLimiter(capacity=1, refill_rate_per_sec=0.0)
        assert await limiter.allow("user1") is True
        assert await limiter.allow("user2") is True
        assert await limiter.allow("user1") is False
        assert await limiter.allow("user2") is False

    async def test_refill_restores_tokens_over_time(self) -> None:
        import time

        limiter = InMemoryRateLimiter(capacity=1, refill_rate_per_sec=100.0)  # 100/sec = fast refill
        assert await limiter.allow("u") is True
        assert await limiter.allow("u") is False
        time.sleep(0.05)  # 50ms → 5 tokens worth (capped at capacity=1)
        assert await limiter.allow("u") is True


# ---- Integration: rate limit applied at /agent/chat ----


class TestAgentRateLimit:
    async def test_under_limit_passes(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        client.set_rate_limiter(InMemoryRateLimiter(capacity=2, refill_rate_per_sec=0.0))  # type: ignore[attr-defined]
        stub = StubAnthropic(
            [
                _Response(content=[_Block(type="text", text="ok")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)
        response = await client.post("/agent/chat", json={"message": "x"}, headers=auth(token))
        assert response.status_code == 200

    async def test_over_limit_returns_429(self, client: AsyncClient) -> None:
        token = await register_and_login(client)
        client.set_rate_limiter(InMemoryRateLimiter(capacity=1, refill_rate_per_sec=0.0))  # type: ignore[attr-defined]
        # Anthropic stub only consumed on the first allowed call
        stub = StubAnthropic(
            [
                _Response(content=[_Block(type="text", text="ok")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)
        # First call passes
        r1 = await client.post("/agent/chat", json={"message": "x"}, headers=auth(token))
        assert r1.status_code == 200
        # Second call gets bounced before reaching the agent
        r2 = await client.post("/agent/chat", json={"message": "x"}, headers=auth(token))
        assert r2.status_code == 429
        assert "rate limit" in r2.json()["detail"].lower()

    async def test_per_user_isolation(self, client: AsyncClient) -> None:
        token_a = await register_and_login(client, "a@example.com")
        token_b = await register_and_login(client, "b@example.com")
        client.set_rate_limiter(InMemoryRateLimiter(capacity=1, refill_rate_per_sec=0.0))  # type: ignore[attr-defined]
        stub = StubAnthropic(
            [
                _Response(content=[_Block(type="text", text="a")], stop_reason="end_turn"),
                _Response(content=[_Block(type="text", text="b")], stop_reason="end_turn"),
            ]
        )
        _override_agent(stub, client)
        # Both users get their first request through (separate buckets)
        r_a = await client.post("/agent/chat", json={"message": "x"}, headers=auth(token_a))
        r_b = await client.post("/agent/chat", json={"message": "x"}, headers=auth(token_b))
        assert r_a.status_code == 200
        assert r_b.status_code == 200
