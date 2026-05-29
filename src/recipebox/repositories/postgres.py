import json

import asyncpg
from pydantic import EmailStr

from recipebox.domain.schemas import Page, Recipe, RecipeCreate, RecipeUpdate, TagCount, UserInDB
from recipebox.repositories.base import RecipeRepository, UserRepository


class PostgresUserRepository(UserRepository):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create(self, email: EmailStr, password_hash: str) -> UserInDB:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO users (email, hashed_password) VALUES ($1, $2) RETURNING *",
                email,
                password_hash,
            )
        if row is None:
            raise RuntimeError("Failed to return a row")
        return UserInDB(**dict(row))

    async def get_by_email(self, email: EmailStr) -> UserInDB | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
        return UserInDB(**dict(row)) if row else None

    async def get_by_id(self, user_id: int) -> UserInDB | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return UserInDB(**dict(row)) if row else None


class PostgresRecipeRepository(RecipeRepository):
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    def _to_recipe(self, row: asyncpg.Record) -> Recipe:
        data = dict(row)
        data["ingredients"] = json.loads(data["ingredients"])
        data["difficulty"] = data["difficulty"] or "medium"
        data["prep_time_minutes"] = data["prep_time_minutes"] or 0
        data["cook_time_minutes"] = data["cook_time_minutes"] or 0
        return Recipe(**data)

    async def get(self, recipe_id: int) -> Recipe | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM recipes WHERE id = $1", recipe_id)
        return self._to_recipe(row) if row else None

    async def get_all(self, skip: int = 0, limit: int = 20) -> Page[Recipe]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM recipes ORDER BY created_at DESC LIMIT $1 OFFSET $2", limit, skip)
            total_rows = await conn.fetchval("SELECT COUNT(*) FROM recipes")
        return Page(items=[self._to_recipe(row) for row in rows], total=total_rows, skip=skip, limit=limit)

    async def create(self, data: RecipeCreate, owner_id: int) -> Recipe:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO recipes (owner_id, title, description, ingredients, steps, tools, tags, servings)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                owner_id,
                data.title,
                data.description,
                json.dumps([i.model_dump() for i in data.ingredients]),
                data.steps,
                data.tools,
                data.tags,
                data.servings,
            )
        if row is None:
            raise RuntimeError("Failed to return a row")
        return self._to_recipe(row)

    async def update(self, recipe_id: int, data: RecipeUpdate) -> Recipe | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE recipes
                SET title = COALESCE($1, title),
                    description = COALESCE($2, description),
                    ingredients = COALESCE($3, ingredients),
                    steps = COALESCE($4, steps),
                    tools = COALESCE($5, tools),
                    tags = COALESCE($6, tags),
                    difficulty = COALESCE($7, difficulty),
                    prep_time_minutes = COALESCE($8, prep_time_minutes),
                    cook_time_minutes = COALESCE($9, cook_time_minutes),
                    servings = COALESCE($10, servings),
                    cost_per_serving = COALESCE($11, cost_per_serving),
                    nutrition_per_serving = COALESCE($12, nutrition_per_serving),
                    source_url = COALESCE($13, source_url),
                    updated_at = NOW()
                WHERE id = $14
                RETURNING *
                """,
                data.title,
                data.description,
                json.dumps([i.model_dump() for i in data.ingredients]) if data.ingredients is not None else None,
                data.steps,
                data.tools,
                data.tags,
                data.difficulty,
                data.prep_time_minutes,
                data.cook_time_minutes,
                data.servings,
                data.cost_per_serving,
                json.dumps(data.nutrition_per_serving.model_dump()) if data.nutrition_per_serving else None,
                data.source_url,
                recipe_id,
            )
        return self._to_recipe(row) if row else None

    async def delete(self, recipe_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM recipes WHERE id = $1", recipe_id)
        return result == "DELETE 1"

    async def get_tags(self) -> list[TagCount]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT unnest(tags) AS tag, COUNT(*) AS count FROM recipes GROUP BY tag ORDER BY count DESC"
            )
        return [TagCount(tag=row["tag"], count=row["count"]) for row in rows]
