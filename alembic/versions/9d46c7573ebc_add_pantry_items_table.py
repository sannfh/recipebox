"""add pantry_items table

Revision ID: 9d46c7573ebc
Revises: 8291addcda0a
Create Date: 2026-06-21 20:40:48.042088

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d46c7573ebc"
down_revision: str | Sequence[str] | None = "8291addcda0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pantry_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_pantry_user_name"),
    )


def downgrade() -> None:
    op.drop_table("pantry_items")
