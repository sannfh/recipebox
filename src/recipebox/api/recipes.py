from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from recipebox.core.importer import RecipeImporter
from recipebox.deps import get_current_user, get_importer, get_recipe_search_service, get_recipe_service
from recipebox.domain.schemas import (
    Page,
    Recipe,
    RecipeCreate,
    RecipeImport,
    RecipeUpdate,
    ReferenceRecipeHit,
    UserInDB,
)
from recipebox.domain.services import RecipeSearchService, RecipeService

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.post("", response_model=Recipe, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    body: RecipeCreate,
    service: Annotated[RecipeService, Depends(get_recipe_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> Recipe:
    return await service.create(data=body, owner_id=current_user.id)


@router.post("/import", response_model=Recipe, status_code=status.HTTP_201_CREATED)
async def import_recipe(
    body: RecipeImport,
    service: Annotated[RecipeService, Depends(get_recipe_service)],
    importer: Annotated[RecipeImporter, Depends(get_importer)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> Recipe:
    recipe_data = await importer.extract(str(body.url))
    return await service.create(data=recipe_data, owner_id=current_user.id)


@router.get("/search", response_model=list[ReferenceRecipeHit])
async def search_recipes(
    service: Annotated[RecipeSearchService, Depends(get_recipe_search_service)],
    q: str,
    top_k: int = 5,
) -> list[ReferenceRecipeHit]:
    return await service.search(query=q, top_k=top_k)


@router.get("/{recipe_id}", response_model=Recipe)
async def get_recipe(
    recipe_id: int,
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> Recipe:
    return await service.get(recipe_id)


@router.get("", response_model=Page[Recipe])
async def list_recipes(
    service: Annotated[RecipeService, Depends(get_recipe_service)],
    skip: int = 0,
    limit: int = 20,
) -> Page[Recipe]:
    return await service.get_all(skip=skip, limit=limit)


@router.patch("/{recipe_id}", response_model=Recipe)
async def update_recipe(
    recipe_id: int,
    body: RecipeUpdate,
    service: Annotated[RecipeService, Depends(get_recipe_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> Recipe:
    return await service.update(recipe_id=recipe_id, data=body, current_user_id=current_user.id)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: int,
    service: Annotated[RecipeService, Depends(get_recipe_service)],
    current_user: Annotated[UserInDB, Depends(get_current_user)],
) -> Response:
    await service.delete(recipe_id=recipe_id, current_user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
