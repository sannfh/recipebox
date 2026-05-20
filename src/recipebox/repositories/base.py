from abc import ABC, abstractmethod

from pydantic import EmailStr

from recipebox.domain.schemas import Page, Recipe, RecipeCreate, RecipeUpdate, UserInDB


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


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: int) -> UserInDB | None: ...

    @abstractmethod
    def get_by_email(self, email: EmailStr) -> UserInDB | None: ...

    @abstractmethod
    def create(self, email: str, password_hash: str) -> UserInDB: ...
