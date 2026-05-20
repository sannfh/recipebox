from abc import ABC, abstractmethod

from recipebox.domain.schemas import Page, Recipe, RecipeCreate, RecipeUpdate


class RecipeRepository(ABC):
    @abstractmethod
    def get(self, recipe_id: int) -> Recipe | None: ...

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 20) -> Page[Recipe]: ...

    @abstractmethod
    def create(self, data: RecipeCreate, owner_id: int) -> Recipe: ...

    @abstractmethod
    def update(self, recipe_id: int, data: RecipeUpdate) -> Recipe | None: ...

    @abstractmethod
    def delete(self, recipe_id: int) -> bool: ...
