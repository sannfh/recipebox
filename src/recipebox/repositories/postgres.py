from pydantic import EmailStr
from sqlalchemy import func, text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from recipebox.domain.schemas import (
    Ingredient,
    NutritionInfo,
    Page,
    Recipe,
    RecipeCreate,
    RecipeUpdate,
    TagCount,
    UserInDB,
)
from recipebox.models import Recipe as RecipeModel
from recipebox.models import User as UserModel
from recipebox.repositories.base import RecipeRepository, UserRepository


class PostgresUserRepository(UserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, email: EmailStr, password_hash: str) -> UserInDB:
        user = UserModel(email=email, hashed_password=password_hash)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        assert user.id is not None and user.created_at is not None
        return UserInDB(id=user.id, email=user.email, hashed_password=user.hashed_password, created_at=user.created_at)

    async def get_by_email(self, email: EmailStr) -> UserInDB | None:
        result = await self.session.exec(select(UserModel).where(UserModel.email == email))
        user = result.first()
        if user is None:
            return None
        assert user.id is not None and user.created_at is not None
        return UserInDB(id=user.id, email=user.email, hashed_password=user.hashed_password, created_at=user.created_at)

    async def get_by_id(self, user_id: int) -> UserInDB | None:
        user = await self.session.get(UserModel, user_id)
        if user is None:
            return None
        assert user.id is not None and user.created_at is not None
        return UserInDB(id=user.id, email=user.email, hashed_password=user.hashed_password, created_at=user.created_at)


class PostgresRecipeRepository(RecipeRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_recipe(self, recipe: RecipeModel) -> Recipe:
        assert recipe.id is not None and recipe.created_at is not None
        return Recipe(
            id=recipe.id,
            owner_id=recipe.owner_id,
            title=recipe.title,
            description=recipe.description or "",
            ingredients=[Ingredient(**i) for i in recipe.ingredients],
            steps=recipe.steps,
            tools=recipe.tools or [],
            tags=recipe.tags or [],
            difficulty=recipe.difficulty or "medium",  # type: ignore[arg-type]
            prep_time_minutes=recipe.prep_time_minutes or 0,
            cook_time_minutes=recipe.cook_time_minutes or 0,
            servings=recipe.servings,
            cost_per_serving=recipe.cost_per_serving,
            nutrition_per_serving=NutritionInfo(**recipe.nutrition_per_serving)
            if recipe.nutrition_per_serving
            else None,
            source_url=recipe.source_url,
            created_at=recipe.created_at,
            updated_at=recipe.updated_at,
        )

    async def get(self, recipe_id: int) -> Recipe | None:
        recipe = await self.session.get(RecipeModel, recipe_id)
        return self._to_recipe(recipe) if recipe else None

    async def get_all(self, skip: int = 0, limit: int = 20) -> Page[Recipe]:
        result = await self.session.exec(
            select(RecipeModel).order_by(col(RecipeModel.created_at).desc()).offset(skip).limit(limit)
        )
        recipes = result.all()
        total = await self.session.exec(select(func.count()).select_from(RecipeModel))
        return Page(items=[self._to_recipe(r) for r in recipes], total=total.one(), skip=skip, limit=limit)

    async def create(self, data: RecipeCreate, owner_id: int) -> Recipe:
        recipe = RecipeModel(
            owner_id=owner_id,
            title=data.title,
            description=data.description,
            ingredients=[i.model_dump() for i in data.ingredients],
            steps=data.steps,
            tools=data.tools,
            tags=data.tags,
            difficulty=data.difficulty,
            prep_time_minutes=data.prep_time_minutes,
            cook_time_minutes=data.cook_time_minutes,
            servings=data.servings,
            cost_per_serving=data.cost_per_serving,
            nutrition_per_serving=data.nutrition_per_serving.model_dump() if data.nutrition_per_serving else None,
            source_url=data.source_url,
        )
        self.session.add(recipe)
        await self.session.commit()
        await self.session.refresh(recipe)
        return self._to_recipe(recipe)

    async def update(self, recipe_id: int, data: RecipeUpdate) -> Recipe | None:
        recipe = await self.session.get(RecipeModel, recipe_id)
        if recipe is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if "ingredients" in update_data:
            update_data["ingredients"] = [i.model_dump() for i in data.ingredients]  # type: ignore
        if "nutrition_per_serving" in update_data and data.nutrition_per_serving is not None:
            update_data["nutrition_per_serving"] = data.nutrition_per_serving.model_dump()
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(recipe, field, value)
        self.session.add(recipe)
        await self.session.commit()
        await self.session.refresh(recipe)
        return self._to_recipe(recipe)

    async def delete(self, recipe_id: int) -> bool:
        recipe = await self.session.get(RecipeModel, recipe_id)
        if recipe is None:
            return False
        await self.session.delete(recipe)
        await self.session.commit()
        return True

    async def get_tags(self) -> list[TagCount]:
        result = await self.session.execute(  # type: ignore[arg-type]
            text("SELECT unnest(tags) AS tag, COUNT(*) AS count FROM recipes GROUP BY tag ORDER BY count DESC")
        )
        return [TagCount(tag=tag, count=count) for tag, count in result.all()]
