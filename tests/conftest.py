import os

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from httpx import ASGITransport, AsyncClient

from recipebox.deps import get_recipe_repo, get_user_repo
from recipebox.main import app
from recipebox.repositories.memory import InMemoryRecipeRepository, InMemoryUserRepository


@pytest.fixture
async def client() -> AsyncClient:
    # Create instances once per test — the lambda captures the same object every call
    user_repo = InMemoryUserRepository()
    recipe_repo = InMemoryRecipeRepository()
    app.dependency_overrides[get_user_repo] = lambda: user_repo
    app.dependency_overrides[get_recipe_repo] = lambda: recipe_repo

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
