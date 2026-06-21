"""Load scraped recipes from resources/recipes.db into the reference_recipes Postgres table.

One-shot data loader (not a migration). Idempotent: refuses to run if reference_recipes
already has rows unless --force is passed (which truncates first).

Usage:
    python scripts/load_reference_recipes.py
    python scripts/load_reference_recipes.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine

# Make src/ importable when running as a script from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recipebox.config import settings
from recipebox.models import ReferenceRecipe

SQLITE_PATH = Path(__file__).resolve().parents[1] / "resources" / "recipes.db"
BATCH_SIZE = 1000


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(x) for x in parsed if x]


def _read_sqlite() -> list[dict]:
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT title, description, ingredients, instructions, url,
               source_site, cuisine, category, servings, image_url
          FROM recipes
         WHERE title IS NOT NULL AND url IS NOT NULL
        """
    ).fetchall()
    conn.close()

    out: list[dict] = []
    for r in rows:
        ingredients = _parse_json_list(r["ingredients"])
        instructions = _parse_json_list(r["instructions"])
        # Skip rows without enough text to be useful for RAG
        if not ingredients or not instructions:
            continue
        out.append(
            {
                "title": r["title"],
                "description": r["description"],
                "ingredients": ingredients,
                "instructions": instructions,
                "url": r["url"],
                "source_site": r["source_site"],
                "cuisine": r["cuisine"],
                "category": r["category"],
                "servings": r["servings"],
                "image_url": r["image_url"],
            }
        )
    return out


async def main(force: bool) -> None:
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite source not found: {SQLITE_PATH}")
    if not settings.database_url:
        raise SystemExit("APP_DATABASE_URL is not set")

    print(f"Reading {SQLITE_PATH}...")
    t0 = time.perf_counter()
    rows = _read_sqlite()
    print(f"  {len(rows):,} usable rows in {time.perf_counter() - t0:.1f}s")

    # ssl=False: Docker Postgres has SSL off; asyncpg's default TLS negotiation crashes
    # on Windows with "OPENSSL_Uplink: no OPENSSL_Applink"
    engine = create_async_engine(settings.database_url, connect_args={"ssl": False})
    async with engine.begin() as conn:
        existing = (await conn.execute(select(func.count()).select_from(ReferenceRecipe))).scalar_one()
        if existing and not force:
            raise SystemExit(f"reference_recipes already has {existing:,} rows — pass --force to truncate and reload")
        if existing and force:
            print(f"  truncating {existing:,} existing rows")
            await conn.execute(text("TRUNCATE TABLE reference_recipes RESTART IDENTITY"))

        print(f"Inserting in batches of {BATCH_SIZE}...")
        t0 = time.perf_counter()
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i : i + BATCH_SIZE]
            await conn.execute(insert(ReferenceRecipe), chunk)
            print(f"  {min(i + BATCH_SIZE, len(rows)):>6,} / {len(rows):,}", end="\r")
        print(f"\n  done in {time.perf_counter() - t0:.1f}s")

    await engine.dispose()
    print(f"Loaded {len(rows):,} reference recipes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="truncate and reload if rows already exist")
    args = parser.parse_args()
    asyncio.run(main(force=args.force))
