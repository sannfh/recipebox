"""add pgvector extension and embedding column

Revision ID: b2c41f9d8e5a
Revises: a1f3e8c20b4d
Create Date: 2026-06-21 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "b2c41f9d8e5a"
down_revision: str | Sequence[str] | None = "a1f3e8c20b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "reference_recipes",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    # HNSW index for cosine distance. Built on the empty column now;
    # pgvector incrementally maintains it as rows get embeddings.
    op.execute(
        "CREATE INDEX reference_recipes_embedding_hnsw_idx "
        "ON reference_recipes USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS reference_recipes_embedding_hnsw_idx")
    op.drop_column("reference_recipes", "embedding")
