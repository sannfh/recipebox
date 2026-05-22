from abc import ABC, abstractmethod

from pydantic import EmailStr

from recipebox.domain.schemas import Page, Recipe, RecipeCreate, RecipeUpdate, UserInDB


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


class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: int) -> UserInDB | None: ...

    @abstractmethod
    async def get_by_email(self, email: EmailStr) -> UserInDB | None: ...

    @abstractmethod
    async def create(self, email: str, password_hash: str) -> UserInDB: ...
