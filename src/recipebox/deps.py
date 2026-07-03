from functools import lru_cache
from typing import Annotated, Any

import redis.asyncio as aioredis
from anthropic import AsyncAnthropic
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from recipebox.config import settings
from recipebox.core.agent import Agent, Tool, build_anthropic_client
from recipebox.core.cache import (
    EMBED_STATS,
    RAG_STATS,
    Cache,
    CachingEmbedder,
    CachingSearchRepository,
    RedisCache,
    build_redis_client,
)
from recipebox.core.embeddings import Embedder, OpenAIEmbedder
from recipebox.core.importer import RecipeImporter
from recipebox.core.rate_limit import AlwaysAllow, RateLimiter, RedisTokenBucket
from recipebox.core.security import decode_access_token
from recipebox.domain.schemas import UserInDB
from recipebox.domain.services import PantryService, RecipeSearchService, RecipeService, UserService
from recipebox.repositories.base import (
    PantryRepository,
    RecipeRepository,
    ReferenceRecipeRepository,
    UserRepository,
)
from recipebox.repositories.postgres import (
    PostgresPantryRepository,
    PostgresRecipeRepository,
    PostgresReferenceRecipeRepository,
    PostgresUserRepository,
)

from .database import SessionLocal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_session():
    assert SessionLocal is not None, "Database not configured"
    async with SessionLocal() as session:
        yield session


def get_recipe_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> PostgresRecipeRepository:
    return PostgresRecipeRepository(session=session)


def get_user_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> PostgresUserRepository:
    return PostgresUserRepository(session=session)


def get_user_service(repo: Annotated[UserRepository, Depends(get_user_repo)]) -> UserService:
    return UserService(repo)


def get_recipe_service(repo: Annotated[RecipeRepository, Depends(get_recipe_repo)]) -> RecipeService:
    return RecipeService(repo)


def get_pantry_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> PostgresPantryRepository:
    return PostgresPantryRepository(session=session)


def get_pantry_service(repo: Annotated[PantryRepository, Depends(get_pantry_repo)]) -> PantryService:
    return PantryService(repo)


def get_reference_recipe_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostgresReferenceRecipeRepository:
    return PostgresReferenceRecipeRepository(session=session)


@lru_cache(maxsize=1)
def _redis_client_singleton() -> aioredis.Redis | None:
    """One pool per process. None if Redis isn't configured (tests, CI)."""
    if not settings.redis_url:
        return None
    return build_redis_client(settings.redis_url)


def get_cache() -> Cache | None:
    client = _redis_client_singleton()
    return RedisCache(client) if client else None


def get_embedder(cache: Annotated[Cache | None, Depends(get_cache)]) -> Embedder:
    inner = OpenAIEmbedder()
    return CachingEmbedder(inner=inner, cache=cache, stats=EMBED_STATS) if cache else inner


def get_recipe_search_service(
    repo: Annotated[ReferenceRecipeRepository, Depends(get_reference_recipe_repo)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    cache: Annotated[Cache | None, Depends(get_cache)],
) -> RecipeSearchService:
    # Wrap the repo too so we cache the (query_vec, top_k) → hits leg as well —
    # skips pgvector on hit, not just OpenAI.
    cached_repo = CachingSearchRepository(inner=repo, cache=cache, stats=RAG_STATS) if cache else repo
    return RecipeSearchService(repo=cached_repo, embedder=embedder)


def get_rate_limiter() -> RateLimiter:
    client = _redis_client_singleton()
    if not client:
        return AlwaysAllow()
    rpm = settings.agent_rate_limit_per_minute
    return RedisTokenBucket(client=client, capacity=rpm, refill_rate_per_sec=rpm / 60.0)


def get_importer() -> RecipeImporter:
    return RecipeImporter()


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> UserInDB:
    token_data = decode_access_token(token)
    if token_data is None or token_data.email is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = await user_repo.get_by_email(token_data.email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def get_anthropic_client() -> AsyncAnthropic:
    return build_anthropic_client()


def get_agent(
    client: Annotated[AsyncAnthropic, Depends(get_anthropic_client)],
    search_service: Annotated[RecipeSearchService, Depends(get_recipe_search_service)],
    reference_repo: Annotated[ReferenceRecipeRepository, Depends(get_reference_recipe_repo)],
    pantry_service: Annotated[PantryService, Depends(get_pantry_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> Agent:
    """Build a per-request Agent. Tool handlers are closures that bake in current_user.id
    so pantry access is automatically scoped to the authenticated user."""

    async def _search_recipes(inp: dict[str, Any]) -> list[dict[str, Any]]:
        query = inp["query"]
        top_k = min(int(inp.get("top_k", 5)), 10)
        hits = await search_service.search(query=query, top_k=top_k)
        return [
            {"id": h.id, "title": h.title, "url": h.url, "source_site": h.source_site, "score": round(h.score, 3)}
            for h in hits
        ]

    async def _get_pantry(inp: dict[str, Any]) -> list[dict[str, Any]]:
        items = await pantry_service.list(user_id=current_user.id)
        return [{"name": i.name, "quantity": i.quantity, "unit": i.unit} for i in items]

    async def _get_recipe_details(inp: dict[str, Any]) -> dict[str, Any] | None:
        detail = await reference_repo.get_detail(int(inp["recipe_id"]))
        return detail.model_dump() if detail else None

    tools = [
        Tool(
            schema={
                "name": "search_recipes",
                "description": (
                    "Semantic search over a verified corpus of 16,000+ recipes. "
                    "Returns ranked hits with id, title, url, and similarity score."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural-language description of what to cook."},
                        "top_k": {"type": "integer", "description": "Number of results (max 10).", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            handler=_search_recipes,
            cites_recipes=True,
        ),
        Tool(
            schema={
                "name": "get_pantry",
                "description": "Return the current user's pantry inventory: list of {name, quantity, unit}.",
                "input_schema": {"type": "object", "properties": {}},
            },
            handler=_get_pantry,
        ),
        Tool(
            schema={
                "name": "get_recipe_details",
                "description": "Fetch full ingredients and instructions for a recipe by its numeric id.",
                "input_schema": {
                    "type": "object",
                    "properties": {"recipe_id": {"type": "integer"}},
                    "required": ["recipe_id"],
                },
            },
            handler=_get_recipe_details,
            cites_recipes=True,
        ),
    ]
    return Agent(client=client, model=settings.anthropic_model, tools=tools)
