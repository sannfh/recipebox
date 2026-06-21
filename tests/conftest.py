import os

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from httpx import ASGITransport, AsyncClient

from recipebox.core.embeddings import Embedder
from recipebox.deps import get_embedder, get_pantry_repo, get_recipe_repo, get_reference_recipe_repo, get_user_repo
from recipebox.main import app
from recipebox.repositories.memory import (
    InMemoryPantryRepository,
    InMemoryRecipeRepository,
    InMemoryReferenceRecipeRepository,
    InMemoryUserRepository,
)


class StubEmbedder(Embedder):
    """Returns deterministic vectors keyed by exact-match text.

    Tests pre-register expected query strings + reference texts so cosine ranking
    is predictable without calling OpenAI.
    """

    def __init__(self, fixed: dict[str, list[float]] | None = None) -> None:
        self.fixed: dict[str, list[float]] = fixed or {}

    async def embed(self, text: str) -> list[float]:
        if text in self.fixed:
            return self.fixed[text]
        return [0.0] * 1536


@pytest.fixture
async def client() -> AsyncClient:
    # Create instances once per test — the lambda captures the same object every call
    user_repo = InMemoryUserRepository()
    recipe_repo = InMemoryRecipeRepository()
    pantry_repo = InMemoryPantryRepository()
    reference_repo = InMemoryReferenceRecipeRepository()
    embedder = StubEmbedder()
    app.dependency_overrides[get_user_repo] = lambda: user_repo
    app.dependency_overrides[get_recipe_repo] = lambda: recipe_repo
    app.dependency_overrides[get_pantry_repo] = lambda: pantry_repo
    app.dependency_overrides[get_reference_recipe_repo] = lambda: reference_repo
    app.dependency_overrides[get_embedder] = lambda: embedder

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.reference_repo = reference_repo  # type: ignore[attr-defined]  # let tests seed it
        ac.embedder = embedder  # type: ignore[attr-defined]
        yield ac

    app.dependency_overrides.clear()
