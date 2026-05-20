from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int


class Ingredient(BaseModel):
    name: str
    amount: float
    unit: str


class NutritionInfo(BaseModel):
    calories: float = Field(ge=0)
    protein_grams: float = Field(ge=0)
    carbs_grams: float = Field(ge=0)
    fat_grams: float = Field(ge=0)
    fiber_grams: float | None = Field(default=None, ge=0)


class RecipeBase(BaseModel):
    title: str
    description: str
    ingredients: list[Ingredient]  # nested model — Pydantic handles this
    steps: list[str]
    tools: list[str] = []  # e.g. ["large pot", "colander", "wooden spoon"]
    tags: list[str] = []
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    prep_time_minutes: int = 0
    cook_time_minutes: int = 0
    servings: int
    cost_per_serving: Decimal | None = Field(default=None, ge=0)  # in whatever currency you use
    nutrition_per_serving: NutritionInfo | None = None  # nested model, fully optional
    source_url: str | None = None

    @computed_field
    @property
    def total_time_minutes(self) -> int:
        return self.prep_time_minutes + self.cook_time_minutes

    @field_validator("tags")
    @classmethod
    def normalized_tags(cls, v: list[str]) -> list[str]:
        return [t.lower().strip() for t in v if t.strip()]

    @field_validator("tools")
    @classmethod
    def normalized_tools(cls, v: list[str]) -> list[str]:
        return [t.lower().strip() for t in v if t.strip()]


class RecipeCreate(RecipeBase):
    pass  # all fields are inherited from RecipeBase, no changes needed


class Recipe(RecipeBase):
    id: int  # unique identifier for the recipe, assigned by the database
    owner_id: int  # foreign key to the user who created the recipe
    created_at: datetime  # timestamp for when the recipe was created
    updated_at: datetime  # timestamp for when the recipe was last updated


class RecipeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    ingredients: list[Ingredient] | None = None
    steps: list[str] | None = None
    tools: list[str] | None = None
    tags: list[str] | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    prep_time_minutes: int | None = Field(default=None, ge=0)
    cook_time_minutes: int | None = Field(default=None, ge=0)
    servings: int | None = Field(default=None, ge=1)
    cost_per_serving: float | None = Field(default=None, ge=0)
    nutrition_per_serving: NutritionInfo | None = None
    source_url: str | None = None


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    created_at: datetime


class UserInDB(User):
    hashed_password: str
