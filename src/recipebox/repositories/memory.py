import math
from collections import Counter
from datetime import UTC, datetime

from pydantic import EmailStr

from recipebox.domain.schemas import (
    Page,
    PantryItem,
    PantryItemCreate,
    PantryItemUpdate,
    Recipe,
    RecipeCreate,
    RecipeUpdate,
    ReferenceRecipeHit,
    TagCount,
    UserInDB,
)
from recipebox.repositories.base import (
    PantryRepository,
    RecipeRepository,
    ReferenceRecipeRepository,
    UserRepository,
)


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


class InMemoryPantryRepository(PantryRepository):
    def __init__(self) -> None:
        self._store: dict[int, PantryItem] = {}
        self._next_id: int = 1

    async def list_for_user(self, user_id: int) -> list[PantryItem]:
        return [item for item in self._store.values() if item.user_id == user_id]

    async def get(self, item_id: int) -> PantryItem | None:
        return self._store.get(item_id)

    async def get_by_name(self, user_id: int, name: str) -> PantryItem | None:
        return next(
            (item for item in self._store.values() if item.user_id == user_id and item.name == name),
            None,
        )

    async def create(self, user_id: int, data: PantryItemCreate) -> PantryItem:
        item = PantryItem(
            id=self._next_id,
            user_id=user_id,
            added_at=datetime.now(UTC),
            **data.model_dump(),
        )
        self._store[self._next_id] = item
        self._next_id += 1
        return item

    async def update(self, item_id: int, data: PantryItemUpdate) -> PantryItem | None:
        item = self._store.get(item_id)
        if item is None:
            return None
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        updated = item.model_copy(update=updates)
        self._store[item_id] = updated
        return updated

    async def delete(self, item_id: int) -> bool:
        if item_id not in self._store:
            return False
        del self._store[item_id]
        return True


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class InMemoryReferenceRecipeRepository(ReferenceRecipeRepository):
    """Test double — store full hit + vector together, sort by cosine."""

    def __init__(self) -> None:
        self._store: list[tuple[ReferenceRecipeHit, list[float]]] = []

    def add(self, hit: ReferenceRecipeHit, vector: list[float]) -> None:
        self._store.append((hit, vector))

    async def search_by_vector(self, query_vec: list[float], top_k: int) -> list[ReferenceRecipeHit]:
        scored = [(hit.model_copy(update={"score": _cosine(query_vec, vec)}), vec) for hit, vec in self._store]
        scored.sort(key=lambda pair: pair[0].score, reverse=True)
        return [hit for hit, _ in scored[:top_k]]
