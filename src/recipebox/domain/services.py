from recipebox.core.security import hash_password, verify_password
from recipebox.domain.errors import (
    AuthenticationError,
    DuplicateEmailError,
    DuplicatePantryItemError,
    ForbiddenError,
    PantryItemNotFoundError,
    RecipeNotFoundError,
)
from recipebox.domain.schemas import (
    Page,
    PantryItem,
    PantryItemCreate,
    PantryItemUpdate,
    Recipe,
    RecipeCreate,
    RecipeUpdate,
    TagCount,
    UserInDB,
)
from recipebox.repositories.base import PantryRepository, RecipeRepository, UserRepository


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

    async def get_all(self, skip: int, limit: int) -> Page[Recipe]:
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

    async def get_tags(self) -> list[TagCount]:
        return await self._repo.get_tags()

    async def delete(self, recipe_id: int, current_user_id: int) -> None:
        recipe = await self._repo.get(recipe_id)
        if recipe is None:
            raise RecipeNotFoundError(f"Recipe {recipe_id} not found")
        if recipe.owner_id != current_user_id:
            raise ForbiddenError("You do not own this recipe")
        await self._repo.delete(recipe_id)


class PantryService:
    def __init__(self, repo: PantryRepository) -> None:
        self._repo = repo

    async def list(self, user_id: int) -> list[PantryItem]:
        return await self._repo.list_for_user(user_id)

    async def add(self, user_id: int, data: PantryItemCreate) -> PantryItem:
        existing = await self._repo.get_by_name(user_id, data.name)
        if existing is not None:
            raise DuplicatePantryItemError(f"Pantry already contains '{data.name}' — update its quantity instead")
        return await self._repo.create(user_id=user_id, data=data)

    async def update(self, item_id: int, current_user_id: int, data: PantryItemUpdate) -> PantryItem:
        item = await self._repo.get(item_id)
        if item is None:
            raise PantryItemNotFoundError(f"Pantry item {item_id} not found")
        if item.user_id != current_user_id:
            raise ForbiddenError("You do not own this pantry item")
        updated = await self._repo.update(item_id, data)
        if updated is None:
            raise PantryItemNotFoundError(f"Pantry item {item_id} not found")
        return updated

    async def delete(self, item_id: int, current_user_id: int) -> None:
        item = await self._repo.get(item_id)
        if item is None:
            raise PantryItemNotFoundError(f"Pantry item {item_id} not found")
        if item.user_id != current_user_id:
            raise ForbiddenError("You do not own this pantry item")
        await self._repo.delete(item_id)
