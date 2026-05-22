from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from recipebox.core.security import Token, create_access_token, hash_password, verify_password
from recipebox.deps import get_current_user, get_user_repo
from recipebox.domain.errors import AuthenticationError, DuplicateEmailError
from recipebox.domain.schemas import User, UserCreate, UserInDB
from recipebox.repositories.base import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> UserInDB:
    existing = await user_repo.get_by_email(body.email)
    if existing is not None:
        raise DuplicateEmailError("Email already registered")

    hashed = hash_password(body.password)
    return await user_repo.create(email=body.email, password_hash=hashed)


@router.post("/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_repo: Annotated[UserRepository, Depends(get_user_repo)],
) -> Token:
    user = await user_repo.get_by_email(form.username)
    if user is None or not verify_password(form.password, user.hashed_password):
        raise AuthenticationError("Invalid credentials")

    return Token(access_token=create_access_token(user.email), token_type="bearer")


@router.get("/me", response_model=User)
async def me(current_user: Annotated[UserInDB, Depends(get_current_user)]) -> UserInDB:
    return current_user
