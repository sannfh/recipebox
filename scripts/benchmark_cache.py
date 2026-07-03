"""Benchmark cache hit rate + latency improvement on /recipes/search.

Hits the live app endpoint with a fixed set of queries, repeated N times each.
First run of each query: cache miss (OpenAI + pgvector). Subsequent runs: cache hit.

Reports for the resume bullet:
  - p50 / p95 / p99 cold vs warm latency
  - Cache hit rate
"""

from __future__ import annotations

import asyncio
import statistics
import time

import httpx

# No truststore — we hit http://localhost so no TLS is involved.

BASE_URL = "http://localhost:8000"
QUERIES = [
    "quick weeknight pasta",
    "vegetarian indian curry",
    "comforting winter soup",
    "easy chocolate dessert",
    "spicy mexican tacos",
    "healthy mediterranean salad",
    "asian stir fry with chicken",
    "slow cooker beef stew",
]
RUNS_PER_QUERY = 5  # 1 cold + 4 warm each
TOP_K = 5


async def time_search(client: httpx.AsyncClient, query: str) -> float:
    t0 = time.perf_counter()
    r = await client.get("/recipes/search", params={"q": query, "top_k": TOP_K})
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000.0


def summarize(latencies: list[float], label: str) -> None:
    if not latencies:
        return
    s = sorted(latencies)
    p50 = statistics.median(s)
    p95 = s[max(0, int(len(s) * 0.95) - 1)]
    p99 = s[max(0, int(len(s) * 0.99) - 1)]
    print(f"  {label:>8}: n={len(s):3d}  p50={p50:7.1f}ms  p95={p95:7.1f}ms  p99={p99:7.1f}ms")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # Reset stats: just read them and compute deltas
        stats0 = (await client.get("/agent/cache-stats")).json()

        cold: list[float] = []
        warm: list[float] = []

        for q in QUERIES:
            for run in range(RUNS_PER_QUERY):
                ms = await time_search(client, q)
                (cold if run == 0 else warm).append(ms)

        stats1 = (await client.get("/agent/cache-stats")).json()
        delta_hits = stats1["embeddings"]["hits"] - stats0["embeddings"]["hits"]
        delta_misses = stats1["embeddings"]["misses"] - stats0["embeddings"]["misses"]
        delta_total = delta_hits + delta_misses
        hit_rate = (delta_hits / delta_total) if delta_total else 0.0

        print()
        print("=" * 64)
        print(f"Benchmark: {len(QUERIES)} queries x {RUNS_PER_QUERY} runs = {len(QUERIES) * RUNS_PER_QUERY} requests")
        print("=" * 64)
        summarize(cold, "cold")
        summarize(warm, "warm")
        if cold and warm:
            p95_cold = sorted(cold)[max(0, int(len(cold) * 0.95) - 1)]
            p95_warm = sorted(warm)[max(0, int(len(warm) * 0.95) - 1)]
            reduction = (1 - p95_warm / p95_cold) * 100 if p95_cold else 0.0
            print()
            print(f"  p95 latency cut by {reduction:.0f}%  ({p95_cold:.0f}ms → {p95_warm:.0f}ms)")
        print(f"  embedding cache hit rate: {hit_rate * 100:.0f}%  ({delta_hits} hits / {delta_total} requests)")
        rag = stats1["rag"]
        rag0 = stats0["rag"]
        rag_delta = (rag["hits"] - rag0["hits"]) + (rag["misses"] - rag0["misses"])
        rag_hits = rag["hits"] - rag0["hits"]
        rag_rate = (rag_hits / rag_delta) if rag_delta else 0.0
        print(f"  RAG cache hit rate:       {rag_rate * 100:.0f}%  ({rag_hits} hits / {rag_delta} requests)")
        print("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
