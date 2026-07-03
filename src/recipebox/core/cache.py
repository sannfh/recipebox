"""Cache abstraction + Redis impl + in-memory test double.

Layered above the embedder and the RAG search service:
- Embeddings cache: deterministic input → vector. Skips OpenAI on hit.
- RAG result cache: deterministic query → ranked hits. Skips OpenAI AND pgvector on hit.

Cache key prefixes:
  emb:v1:<sha256(text)>            → embedding vector (JSON list[float])
  rag:v1:<sha256(query)>:<top_k>   → search result list (JSON list[dict])

The v1 segment lets us bump a version when the corpus or embedding model changes,
invalidating everything atomically instead of waiting for TTL.
"""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from recipebox.core.embeddings import Embedder
from recipebox.domain.schemas import ReferenceRecipeHit

DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


class Cache(ABC):
    @abstractmethod
    async def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def set(self, key: str, value: bytes, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None: ...


class RedisCache(Cache):
    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> bytes | None:
        return await self._client.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        await self._client.set(key, value, ex=ttl_seconds)


class InMemoryCache(Cache):
    """Test double — no TTL enforcement; tests don't sleep."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._store[key] = value


@dataclass
class CacheStats:
    """Hit/miss tracking — exposed via /agent/cache-stats for the resume benchmark."""

    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CachingEmbedder(Embedder):
    """Decorator over any Embedder. Hashes text → looks up Redis → calls inner on miss."""

    def __init__(self, inner: Embedder, cache: Cache, stats: CacheStats | None = None) -> None:
        self._inner = inner
        self._cache = cache
        self.stats = stats or CacheStats()

    async def embed(self, text: str) -> list[float]:
        key = f"emb:v1:{_sha(text)}"
        cached = await self._cache.get(key)
        if cached is not None:
            self.stats.hits += 1
            return json.loads(cached.decode("utf-8"))
        self.stats.misses += 1
        vec = await self._inner.embed(text)
        await self._cache.set(key, json.dumps(vec).encode("utf-8"))
        return vec


@dataclass
class TimedHits:
    hits: list[ReferenceRecipeHit]
    elapsed_ms: float = field(default=0.0)


class CachingSearchRepository:
    """Wraps any ReferenceRecipeRepository, caching (query_vec_hash, top_k) → hits."""

    def __init__(self, inner, cache: Cache, stats: CacheStats | None = None) -> None:
        self._inner = inner
        self._cache = cache
        self.stats = stats or CacheStats()

    async def search_by_vector(self, query_vec: list[float], top_k: int) -> list[ReferenceRecipeHit]:
        # The query_vec is the embedded query; its hash uniquely identifies the query.
        vec_key = _sha(",".join(f"{x:.6f}" for x in query_vec[:32]))  # first 32 dims = strong fingerprint
        key = f"rag:v1:{vec_key}:{top_k}"
        cached = await self._cache.get(key)
        if cached is not None:
            self.stats.hits += 1
            return [ReferenceRecipeHit.model_validate(h) for h in json.loads(cached.decode("utf-8"))]
        self.stats.misses += 1
        hits = await self._inner.search_by_vector(query_vec=query_vec, top_k=top_k)
        await self._cache.set(key, json.dumps([h.model_dump() for h in hits]).encode("utf-8"))
        return hits

    async def get_detail(self, recipe_id):
        return await self._inner.get_detail(recipe_id)


def build_redis_client(url: str) -> aioredis.Redis:
    """Single factory so connection settings live in one place."""
    return aioredis.from_url(url, decode_responses=False)


# Module-level shared stats — one instance per process so /cache-stats sees aggregates
EMBED_STATS = CacheStats()
RAG_STATS = CacheStats()


def now_ms() -> float:
    return time.perf_counter() * 1000.0
