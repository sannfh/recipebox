from abc import ABC, abstractmethod

from pydantic import EmailStr

from recipebox.domain.schemas import (
    Page,
    PantryItem,
    PantryItemCreate,
    PantryItemUpdate,
    Recipe,
    RecipeCreate,
    RecipeUpdate,
    ReferenceRecipeDetail,
    ReferenceRecipeHit,
    TagCount,
    UserInDB,
)


class RecipeRepository(ABC):
    @abstractmethod
    async def get(self, recipe_id: int) -> Recipe | None: ...

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 20) -> Page[Recipe]: ...

    @abstractmethod
    async def create(self, data: RecipeCreate, owner_id: int) -> Recipe: ...

    @abstractmethod
    async def update(self, recipe_id: int, data: RecipeUpdate) -> Recipe | None: ...

    @abstractmethod
    async def delete(self, recipe_id: int) -> bool: ...

    @abstractmethod
    async def get_tags(self) -> list[TagCount]: ...


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: int) -> UserInDB | None: ...

    @abstractmethod
    async def get_by_email(self, email: EmailStr) -> UserInDB | None: ...

    @abstractmethod
    async def create(self, email: str, password_hash: str) -> UserInDB: ...


class ReferenceRecipeRepository(ABC):
    @abstractmethod
    async def search_by_vector(self, query_vec: list[float], top_k: int) -> list[ReferenceRecipeHit]: ...

    @abstractmethod
    async def get_detail(self, recipe_id: int) -> ReferenceRecipeDetail | None: ...


class PantryRepository(ABC):
    @abstractmethod
    async def list_for_user(self, user_id: int) -> list[PantryItem]: ...

    @abstractmethod
    async def get(self, item_id: int) -> PantryItem | None: ...

    @abstractmethod
    async def get_by_name(self, user_id: int, name: str) -> PantryItem | None: ...

    @abstractmethod
    async def create(self, user_id: int, data: PantryItemCreate) -> PantryItem: ...

    @abstractmethod
    async def update(self, item_id: int, data: PantryItemUpdate) -> PantryItem | None: ...

    @abstractmethod
    async def delete(self, item_id: int) -> bool: ...
