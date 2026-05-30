"""initial

Revision ID: 8291addcda0a
Revises:
Create Date: 2026-05-30 01:07:24.822033

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8291addcda0a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    pass
    # ### end Alembic commands ###
