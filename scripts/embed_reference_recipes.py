"""Embed reference_recipes whose embedding is NULL using OpenAI text-embedding-3-small.

Idempotent: only embeds rows missing an embedding. Safe to re-run if interrupted.

Usage:
    python scripts/embed_reference_recipes.py
    python scripts/embed_reference_recipes.py --batch 100 --limit 500   # cap for a dry run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import truststore
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

# Use the OS cert store for HTTPS; avoids "OPENSSL_Uplink no OPENSSL_Applink"
# crashes on Windows when openai/httpx loads its bundled OpenSSL.
truststore.inject_into_ssl()

from openai import AsyncOpenAI  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recipebox.config import settings  # noqa: E402
from recipebox.models import EMBEDDING_DIM, ReferenceRecipe  # noqa: E402

# Char cap ≈ 6500 tokens, well under the 8191 input limit for text-embedding-3-small
MAX_CHARS = 26000


def build_text(r: ReferenceRecipe) -> str:
    parts = [r.title]
    if r.description:
        parts.append(r.description)
    if r.ingredients:
        parts.append("Ingredients: " + "; ".join(r.ingredients))
    if r.instructions:
        parts.append("Instructions: " + " ".join(r.instructions))
    text = "\n".join(parts).replace("\x00", "")
    return text[:MAX_CHARS]


async def embed_batch(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    resp = await client.embeddings.create(model=settings.embedding_model, input=texts)
    return [d.embedding for d in resp.data]


async def main(batch_size: int, limit: int | None) -> None:
    if not settings.openai_api_key:
        raise SystemExit("APP_OPENAI_API_KEY is not set")
    if not settings.database_url:
        raise SystemExit("APP_DATABASE_URL is not set")

    engine = create_async_engine(settings.database_url, connect_args={"ssl": False})
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # max_retries with built-in exponential backoff handles 429 TPM bursts
    # (16k recipes ≈ 8M tokens, OpenAI free-tier TPM cap is 1M).
    client = AsyncOpenAI(api_key=settings.openai_api_key, max_retries=10)

    async with session_factory() as session:
        stmt = select(ReferenceRecipe).where(ReferenceRecipe.embedding.is_(None)).order_by(ReferenceRecipe.id)  # type: ignore[union-attr]
        if limit:
            stmt = stmt.limit(limit)
        rows = (await session.exec(stmt)).all()

    total = len(rows)
    if total == 0:
        print("Nothing to embed — all reference_recipes already have embeddings.")
        await engine.dispose()
        await client.close()
        return

    print(f"Embedding {total:,} recipes in batches of {batch_size} (model={settings.embedding_model})")
    t0 = time.perf_counter()
    done = 0

    for i in range(0, total, batch_size):
        chunk = rows[i : i + batch_size]
        texts = [build_text(r) for r in chunk]
        vectors = await embed_batch(client, texts)
        assert len(vectors) == len(chunk)
        assert all(len(v) == EMBEDDING_DIM for v in vectors)

        payload = [{"id": r.id, "embedding": v} for r, v in zip(chunk, vectors, strict=True)]
        async with session_factory() as session:
            await session.execute(update(ReferenceRecipe), payload)
            await session.commit()

        done += len(chunk)
        elapsed = time.perf_counter() - t0
        rate = done / elapsed if elapsed else 0
        eta = (total - done) / rate if rate else 0
        print(f"  {done:>6,} / {total:,}  ({rate:5.1f} rec/s, ETA {eta / 60:4.1f}m)", end="\r")

    print(f"\n  done in {(time.perf_counter() - t0) / 60:.1f}m")
    await engine.dispose()
    await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=100, help="OpenAI batch size (default 100)")
    parser.add_argument("--limit", type=int, default=None, help="cap rows for a dry run")
    args = parser.parse_args()
    asyncio.run(main(batch_size=args.batch, limit=args.limit))
