import pytest

from recipebox.domain.schemas import RecipeCreate, RecipeUpdate
from recipebox.repositories.memory import InMemoryRecipeRepository, InMemoryUserRepository

# --- fixtures ---


@pytest.fixture
def recipe_repo() -> InMemoryRecipeRepository:
    return InMemoryRecipeRepository()


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


def make_recipe(**overrides: object) -> RecipeCreate:
    base: dict[str, object] = {
        "title": "Pasta",
        "description": "Simple pasta",
        "ingredients": [{"name": "pasta", "amount": 200, "unit": "grams"}],
        "steps": ["Boil water", "Cook pasta"],
        "servings": 2,
    }
    return RecipeCreate.model_validate({**base, **overrides})


# --- InMemoryRecipeRepository ---


class TestRecipeCreate:
    async def test_returns_recipe_with_assigned_id(self, recipe_repo: InMemoryRecipeRepository) -> None:
        recipe = await recipe_repo.create(make_recipe(), owner_id=1)
        assert recipe.id == 1

    async def test_ids_increment(self, recipe_repo: InMemoryRecipeRepository) -> None:
        first = await recipe_repo.create(make_recipe(), owner_id=1)
        second = await recipe_repo.create(make_recipe(), owner_id=1)
        assert second.id == first.id + 1

    async def test_stores_owner_id(self, recipe_repo: InMemoryRecipeRepository) -> None:
        recipe = await recipe_repo.create(make_recipe(), owner_id=42)
        assert recipe.owner_id == 42

    async def test_stores_recipe_fields(self, recipe_repo: InMemoryRecipeRepository) -> None:
        recipe = await recipe_repo.create(make_recipe(title="Risotto"), owner_id=1)
        assert recipe.title == "Risotto"


class TestRecipeGet:
    async def test_get_returns_recipe(self, recipe_repo: InMemoryRecipeRepository) -> None:
        created = await recipe_repo.create(make_recipe(), owner_id=1)
        assert await recipe_repo.get(created.id) == created

    async def test_get_returns_none_for_missing_id(self, recipe_repo: InMemoryRecipeRepository) -> None:
        assert await recipe_repo.get(999) is None


class TestRecipeGetAll:
    async def test_empty_store_returns_empty_page(self, recipe_repo: InMemoryRecipeRepository) -> None:
        page = await recipe_repo.get_all()
        assert page.items == []
        assert page.total == 0

    async def test_total_reflects_all_recipes(self, recipe_repo: InMemoryRecipeRepository) -> None:
        for _ in range(5):
            await recipe_repo.create(make_recipe(), owner_id=1)
        page = await recipe_repo.get_all(skip=0, limit=2)
        assert page.total == 5
        assert len(page.items) == 2

    async def test_skip_offsets_results(self, recipe_repo: InMemoryRecipeRepository) -> None:
        for _ in range(3):
            await recipe_repo.create(make_recipe(), owner_id=1)
        page = await recipe_repo.get_all(skip=2, limit=10)
        assert len(page.items) == 1

    async def test_skip_past_end_returns_empty_items(self, recipe_repo: InMemoryRecipeRepository) -> None:
        await recipe_repo.create(make_recipe(), owner_id=1)
        page = await recipe_repo.get_all(skip=100, limit=10)
        assert page.items == []
        assert page.total == 1


class TestRecipeUpdate:
    async def test_update_changes_field(self, recipe_repo: InMemoryRecipeRepository) -> None:
        created = await recipe_repo.create(make_recipe(title="Old"), owner_id=1)
        updated = await recipe_repo.update(created.id, RecipeUpdate(title="New"))
        assert updated is not None
        assert updated.title == "New"

    async def test_update_does_not_affect_other_fields(self, recipe_repo: InMemoryRecipeRepository) -> None:
        created = await recipe_repo.create(make_recipe(servings=4), owner_id=1)
        updated = await recipe_repo.update(created.id, RecipeUpdate(title="New"))
        assert updated is not None
        assert updated.servings == 4

    async def test_update_returns_none_for_missing_id(self, recipe_repo: InMemoryRecipeRepository) -> None:
        assert await recipe_repo.update(999, RecipeUpdate(title="X")) is None

    async def test_updated_at_changes_after_update(self, recipe_repo: InMemoryRecipeRepository) -> None:
        created = await recipe_repo.create(make_recipe(), owner_id=1)
        updated = await recipe_repo.update(created.id, RecipeUpdate(title="New"))
        assert updated is not None
        assert updated.updated_at >= created.updated_at


class TestRecipeDelete:
    async def test_delete_removes_recipe(self, recipe_repo: InMemoryRecipeRepository) -> None:
        created = await recipe_repo.create(make_recipe(), owner_id=1)
        await recipe_repo.delete(created.id)
        assert await recipe_repo.get(created.id) is None

    async def test_delete_returns_true_on_success(self, recipe_repo: InMemoryRecipeRepository) -> None:
        created = await recipe_repo.create(make_recipe(), owner_id=1)
        assert await recipe_repo.delete(created.id) is True

    async def test_delete_returns_false_for_missing_id(self, recipe_repo: InMemoryRecipeRepository) -> None:
        assert await recipe_repo.delete(999) is False


# --- InMemoryUserRepository ---


class TestUserCreate:
    async def test_stores_hashed_password(self, user_repo: InMemoryUserRepository) -> None:
        user = await user_repo.create(email="a@example.com", password_hash="hashed123")
        assert user.hashed_password == "hashed123"

    async def test_stores_email(self, user_repo: InMemoryUserRepository) -> None:
        user = await user_repo.create(email="a@example.com", password_hash="x")
        assert user.email == "a@example.com"

    async def test_ids_increment(self, user_repo: InMemoryUserRepository) -> None:
        first = await user_repo.create(email="a@example.com", password_hash="x")
        second = await user_repo.create(email="b@example.com", password_hash="x")
        assert second.id == first.id + 1


class TestUserGet:
    async def test_get_by_id_returns_user(self, user_repo: InMemoryUserRepository) -> None:
        created = await user_repo.create(email="a@example.com", password_hash="x")
        assert await user_repo.get_by_id(created.id) == created

    async def test_get_by_id_returns_none_for_missing(self, user_repo: InMemoryUserRepository) -> None:
        assert await user_repo.get_by_id(999) is None

    async def test_get_by_email_returns_user(self, user_repo: InMemoryUserRepository) -> None:
        created = await user_repo.create(email="a@example.com", password_hash="x")
        assert await user_repo.get_by_email("a@example.com") == created

    async def test_get_by_email_returns_none_for_missing(self, user_repo: InMemoryUserRepository) -> None:
        assert await user_repo.get_by_email("missing@example.com") is None
