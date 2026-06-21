from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

EMBEDDING_DIM = 1536


class User(SQLModel, table=True):
    __tablename__ = "users"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class Recipe(SQLModel, table=True):
    __tablename__ = "recipes"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False))
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    title: str
    description: str | None = None
    ingredients: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    steps: list[str] = Field(sa_column=Column(ARRAY(String), nullable=False))
    tools: list[str] | None = Field(default=None, sa_column=Column(ARRAY(String), nullable=True))
    tags: list[str] | None = Field(default=None, sa_column=Column(ARRAY(String), nullable=True))
    difficulty: str | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    servings: int
    cost_per_serving: Decimal | None = Field(default=None, sa_column=Column(Numeric(7, 2), nullable=True))
    nutrition_per_serving: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    source_url: str | None = None


class ReferenceRecipe(SQLModel, table=True):
    __tablename__ = "reference_recipes"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str | None = None
    ingredients: list[str] = Field(sa_column=Column(JSON, nullable=False))
    instructions: list[str] = Field(sa_column=Column(JSON, nullable=False))
    url: str
    source_site: str | None = None
    cuisine: str | None = None
    category: str | None = None
    servings: str | None = None
    image_url: str | None = None
    embedding: list[float] | None = Field(default=None, sa_column=Column(Vector(EMBEDDING_DIM), nullable=True))


class PantryItem(SQLModel, table=True):
    __tablename__ = "pantry_items"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_pantry_user_name"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False))
    name: str
    quantity: float = Field(sa_column=Column(Float, nullable=False))
    unit: str = ""
    added_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
