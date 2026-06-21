from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from recipebox.deps import get_current_user, get_pantry_service
from recipebox.domain.schemas import PantryItem, PantryItemCreate, PantryItemUpdate, UserInDB
from recipebox.domain.services import PantryService

router = APIRouter(prefix="/pantry", tags=["pantry"])


@router.get("", response_model=list[PantryItem])
async def list_pantry(
    service: Annotated[PantryService, Depends(get_pantry_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> list[PantryItem]:
    return await service.list(user_id=current_user.id)


@router.post("", response_model=PantryItem, status_code=status.HTTP_201_CREATED)
async def add_pantry_item(
    body: PantryItemCreate,
    service: Annotated[PantryService, Depends(get_pantry_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> PantryItem:
    return await service.add(user_id=current_user.id, data=body)


@router.patch("/{item_id}", response_model=PantryItem)
async def update_pantry_item(
    item_id: int,
    body: PantryItemUpdate,
    service: Annotated[PantryService, Depends(get_pantry_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> PantryItem:
    return await service.update(item_id=item_id, current_user_id=current_user.id, data=body)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pantry_item(
    item_id: int,
    service: Annotated[PantryService, Depends(get_pantry_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> Response:
    await service.delete(item_id=item_id, current_user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
