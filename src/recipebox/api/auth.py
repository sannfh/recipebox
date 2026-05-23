from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from recipebox.core.security import Token, create_access_token
from recipebox.deps import get_current_user, get_user_service
from recipebox.domain.schemas import User, UserCreate, UserInDB
from recipebox.domain.services import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserInDB:
    return await service.register(email=body.email, password=body.password)


@router.post("/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[UserService, Depends(get_user_service)],
) -> Token:
    user = await service.authenticate(email=form.username, password=form.password)
    return Token(access_token=create_access_token(user.email), token_type="bearer")


@router.get("/me", response_model=User)
async def me(current_user: Annotated[UserInDB, Depends(get_current_user)]) -> UserInDB:
    return current_user
