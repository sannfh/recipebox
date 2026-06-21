"""add reference_recipes table

Revision ID: a1f3e8c20b4d
Revises: 9d46c7573ebc
Create Date: 2026-06-21 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1f3e8c20b4d"
down_revision: str | Sequence[str] | None = "9d46c7573ebc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("source_site", sa.String(), nullable=True),
        sa.Column("cuisine", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("servings", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("reference_recipes")
