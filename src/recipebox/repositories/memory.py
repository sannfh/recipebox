from collections import Counter
from datetime import UTC, datetime

from pydantic import EmailStr

from recipebox.domain.schemas import Page, Recipe, RecipeCreate, RecipeUpdate, TagCount, UserInDB
from recipebox.repositories.base import RecipeRepository, UserRepository


class InMemoryRecipeRepository(RecipeRepository):
    def __init__(self) -> None:
        self._store: dict[int, Recipe] = {}
        self._next_id: int = 1

    async def get(self, recipe_id: int) -> Recipe | None:
        return self._store.get(recipe_id)

    async def get_all(self, skip: int = 0, limit: int = 20) -> Page[Recipe]:
        all_recipes = list(self._store.values())
        return Page(
            items=all_recipes[skip : skip + limit],
            total=len(all_recipes),
            skip=skip,
            limit=limit,
        )

    async def create(self, data: RecipeCreate, owner_id: int) -> Recipe:
        now = datetime.now(UTC)
        recipe = Recipe(
            id=self._next_id,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )
        self._store[self._next_id] = recipe
        self._next_id += 1
        return recipe

    async def update(self, recipe_id: int, data: RecipeUpdate) -> Recipe | None:
        recipe = self._store.get(recipe_id)
        if recipe is None:
            return None
        updated = recipe.model_copy(update={k: v for k, v in data.model_dump().items() if v is not None})
        updated = updated.model_copy(update={"updated_at": datetime.now(UTC)})
        self._store[recipe_id] = updated
        return updated

    async def delete(self, recipe_id: int) -> bool:
        if recipe_id not in self._store:
            return False
        del self._store[recipe_id]
        return True

    async def get_tags(self) -> list[TagCount]:
        counts = Counter(tag for recipe in self._store.values() for tag in recipe.tags)
        return [TagCount(tag=tag, count=count) for tag, count in counts.most_common()]


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._store: dict[int, UserInDB] = {}
        self._next_id: int = 1

    async def get_by_id(self, user_id: int) -> UserInDB | None:
        return self._store.get(user_id)

    async def get_by_email(self, email: EmailStr) -> UserInDB | None:
        return next((u for u in self._store.values() if u.email == email), None)

    async def create(self, email: str, password_hash: str) -> UserInDB:
        now = datetime.now(UTC)
        user = UserInDB(
            id=self._next_id,
            email=email,
            created_at=now,
            hashed_password=password_hash,
        )
        self._store[self._next_id] = user
        self._next_id += 1
        return user
