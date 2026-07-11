"""A small, real retrieval corpus for evals — no Postgres required.

The production agent searches 16k pgvector rows. For evals we want the *same
retrieval behaviour* without standing up Postgres, so we load a fixed sample of
real recipes from ``resources/recipes.db``, embed them with the real
``OpenAIEmbedder`` (so the vector space matches production), and seed an
``InMemoryReferenceRecipeRepository``. Cosine ranking over ~40 rows is identical
in shape to pgvector's ``<=>`` — just smaller.

Embeddings are cached to ``tests/evals/.corpus_cache.json`` so we only pay the
OpenAI embed cost once. The cache is regenerable and git-ignored.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from recipebox.config import settings
from recipebox.core.embeddings import Embedder, OpenAIEmbedder
from recipebox.domain.schemas import ReferenceRecipeDetail, ReferenceRecipeHit
from recipebox.repositories.memory import InMemoryReferenceRecipeRepository

_ROOT = Path(__file__).resolve().parents[2]
SQLITE_PATH = _ROOT / "resources" / "recipes.db"
CACHE_PATH = Path(__file__).resolve().parent / ".corpus_cache.json"
CONTEXTS_PATH = Path(__file__).resolve().parent / "contexts.json"

# How many real recipes to seed. Needs to be big enough that semantic search has
# genuinely-relevant candidates to return — a too-small corpus starves retrieval
# and tanks ContextualRelevancy for reasons that have nothing to do with the agent.
CORPUS_SIZE = 250

# Cap concurrent embedding requests so seeding a few hundred recipes doesn't burst
# past the OpenAI rate limit.
_EMBED_CONCURRENCY = 16

# Same char cap as scripts/embed_reference_recipes.py.
MAX_CHARS = 26000


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(x) for x in parsed if x]


def _build_text(detail: ReferenceRecipeDetail) -> str:
    """Mirror of scripts/embed_reference_recipes.build_text so the eval corpus
    lands in the same embedding space as the production index."""
    parts = [detail.title]
    if detail.description:
        parts.append(detail.description)
    if detail.ingredients:
        parts.append("Ingredients: " + "; ".join(detail.ingredients))
    if detail.instructions:
        parts.append("Instructions: " + " ".join(detail.instructions))
    return "\n".join(parts).replace("\x00", "")[:MAX_CHARS]


def _read_recipes(limit: int) -> list[tuple[ReferenceRecipeHit, ReferenceRecipeDetail]]:
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, title, description, ingredients, instructions, url,
               source_site, cuisine, category, servings, image_url
          FROM recipes
         WHERE title IS NOT NULL AND url IS NOT NULL
               AND ingredients IS NOT NULL AND instructions IS NOT NULL
         ORDER BY id
        """
    ).fetchall()
    conn.close()

    out: list[tuple[ReferenceRecipeHit, ReferenceRecipeDetail]] = []
    for r in rows:
        ingredients = _parse_json_list(r["ingredients"])
        instructions = _parse_json_list(r["instructions"])
        if not ingredients or not instructions:
            continue
        rid = int(r["id"])
        hit = ReferenceRecipeHit(
            id=rid,
            title=r["title"],
            description=r["description"],
            url=r["url"],
            source_site=r["source_site"],
            cuisine=r["cuisine"],
            category=r["category"],
            image_url=r["image_url"],
            score=0.0,
        )
        detail = ReferenceRecipeDetail(
            id=rid,
            title=r["title"],
            description=r["description"],
            ingredients=ingredients,
            instructions=instructions,
            url=r["url"],
            source_site=r["source_site"],
            cuisine=r["cuisine"],
            category=r["category"],
            servings=r["servings"],
            image_url=r["image_url"],
        )
        out.append((hit, detail))
        if len(out) >= limit:
            break
    return out


def _load_cache() -> dict[str, list[float]]:
    if not CACHE_PATH.exists():
        return {}
    data = json.loads(CACHE_PATH.read_text())
    if data.get("model") != settings.embedding_model:
        return {}  # model changed → cache is stale
    return {int(k): v for k, v in data["vectors"].items()}  # type: ignore[misc]


def _save_cache(vectors: dict[int, list[float]]) -> None:
    CACHE_PATH.write_text(json.dumps({"model": settings.embedding_model, "vectors": vectors}))


async def build_reference_repo(
    embedder: Embedder | None = None, size: int = CORPUS_SIZE
) -> InMemoryReferenceRecipeRepository:
    """Seed an in-memory reference repo with `size` real recipes + real embeddings.

    Reuses cached vectors when present so repeated eval runs don't re-embed.
    """
    embedder = embedder or OpenAIEmbedder()
    pairs = _read_recipes(size)
    cache = _load_cache()

    to_embed = [(hit, detail) for hit, detail in pairs if hit.id not in cache]
    if to_embed:
        sem = asyncio.Semaphore(_EMBED_CONCURRENCY)

        async def _embed_one(text: str) -> list[float]:
            async with sem:
                return await embedder.embed(text)

        new_vectors = await asyncio.gather(*(_embed_one(_build_text(d)) for _, d in to_embed))
        for (hit, _), vec in zip(to_embed, new_vectors, strict=True):
            cache[hit.id] = vec
        _save_cache(cache)

    repo = InMemoryReferenceRecipeRepository()
    for hit, detail in pairs:
        repo.add(hit, cache[hit.id])
        repo.add_detail(detail)
    return repo


def build_contexts_file(size: int = CORPUS_SIZE) -> Path:
    """Write ``contexts.json`` — one context per seeded recipe — as the source for
    ``deepeval generate --method contexts``. Grounding goldens in the *same*
    recipes the eval corpus holds keeps every generated question answerable, so a
    low retrieval score means the agent failed, not that the corpus lacked the dish.

    No embeddings or network needed — pure text.
    """
    pairs = _read_recipes(size)
    contexts = [[_build_text(detail)] for _, detail in pairs]
    CONTEXTS_PATH.write_text(json.dumps(contexts))
    return CONTEXTS_PATH


if __name__ == "__main__":
    path = build_contexts_file()
    print(f"wrote {path} ({CORPUS_SIZE} recipe contexts)")
