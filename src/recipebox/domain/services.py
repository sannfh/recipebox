from recipebox.core.security import hash_password, verify_password
from recipebox.domain.errors import (
    AuthenticationError,
    DuplicateEmailError,
    ForbiddenError,
    RecipeNotFoundError,
)
from recipebox.domain.schemas import Page, Recipe, RecipeCreate, RecipeUpdate, UserInDB
from recipebox.repositories.base import RecipeRepository, UserRepository


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def register(self, email: str, password: str) -> UserInDB:
        existing = await self._repo.get_by_email(email)
        if existing is not None:
            raise DuplicateEmailError("Email already registered")
        return await self._repo.create(email=email, password_hash=hash_password(password))

    async def authenticate(self, email: str, password: str) -> UserInDB:
        user = await self._repo.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials")
        return user


class RecipeService:
    def __init__(self, repo: RecipeRepository) -> None:
        self._repo = repo

    async def create(self, data: RecipeCreate, owner_id: int) -> Recipe:
        return await self._repo.create(data=data, owner_id=owner_id)

    async def get(self, recipe_id: int) -> Recipe:
        recipe = await self._repo.get(recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(f"Recipe {recipe_id} not found")
        return recipe

    async def list(self, skip: int, limit: int) -> Page[Recipe]:
        return await self._repo.get_all(skip=skip, limit=limit)

    async def update(self, recipe_id: int, data: RecipeUpdate, current_user_id: int) -> Recipe:
        recipe = await self._repo.get(recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(f"Recipe {recipe_id} not found")
        if recipe.owner_id != current_user_id:
            raise ForbiddenError("You do not own this recipe")
        updated = await self._repo.update(recipe_id, data)
        if updated is None:
            raise RecipeNotFoundError(f"Recipe {recipe_id} not found")
        return updated

    async def delete(self, recipe_id: int, current_user_id: int) -> None:
        recipe = await self._repo.get(recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(f"Recipe {recipe_id} not found")
        if recipe.owner_id != current_user_id:
            raise ForbiddenError("You do not own this recipe")
        await self._repo.delete(recipe_id)
