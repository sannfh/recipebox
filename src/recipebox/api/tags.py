from typing import Annotated

from fastapi import APIRouter, Depends

from recipebox.deps import get_recipe_service
from recipebox.domain.schemas import TagCount
from recipebox.domain.services import RecipeService

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagCount])
async def list_tags(
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> list[TagCount]:
    return await service.get_tags()
