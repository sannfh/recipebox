from datetime import UTC, datetime

from recipebox.domain.schemas import Recipe, RecipeCreate, RecipeUpdate
from recipebox.repositories.base import RecipeRepository


class InMemoryRecipeRepository(RecipeRepository):
    def __init__(self) -> None:
        self._store: dict[int, Recipe] = {}
        self._next_id: int = 1

    def get(self, recipe_id: int) -> Recipe | None:
        return self._store.get(recipe_id)

    def get_all(self) -> list[Recipe]:
        return list(self._store.values())

    def create(self, data: RecipeCreate, owner_id: int) -> Recipe:
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

    def update(self, recipe_id: int, data: RecipeUpdate) -> Recipe | None:
        recipe = self._store.get(recipe_id)
        if recipe is None:
            return None
        updated = recipe.model_copy(update={k: v for k, v in data.model_dump().items() if v is not None})
        updated = updated.model_copy(update={"updated_at": datetime.now(UTC)})
        self._store[recipe_id] = updated
        return updated

    def delete(self, recipe_id: int) -> bool:
        if recipe_id not in self._store:
            return False
        del self._store[recipe_id]
        return True
