from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from recipebox import database
from recipebox.core.importer import RecipeImporter
from recipebox.core.security import decode_access_token
from recipebox.domain.schemas import UserInDB
from recipebox.domain.services import RecipeService, UserService
from recipebox.repositories.base import RecipeRepository, UserRepository
from recipebox.repositories.postgres import PostgresRecipeRepository, PostgresUserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_recipe_repo() -> PostgresRecipeRepository:
    assert database.pool is not None
    return PostgresRecipeRepository(pool=database.pool)


def get_user_repo() -> UserRepository:
    assert database.pool is not None
    return PostgresUserRepository(pool=database.pool)


def get_user_service(repo: Annotated[UserRepository, Depends(get_user_repo)]) -> UserService:
    return UserService(repo)


def get_recipe_service(repo: Annotated[RecipeRepository, Depends(get_recipe_repo)]) -> RecipeService:
    return RecipeService(repo)


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
