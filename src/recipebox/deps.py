from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from recipebox.core.importer import RecipeImporter
from recipebox.core.security import decode_access_token
from recipebox.domain.schemas import UserInDB
from recipebox.domain.services import PantryService, RecipeService, UserService
from recipebox.repositories.base import PantryRepository, RecipeRepository, UserRepository
from recipebox.repositories.postgres import PostgresPantryRepository, PostgresRecipeRepository, PostgresUserRepository

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
