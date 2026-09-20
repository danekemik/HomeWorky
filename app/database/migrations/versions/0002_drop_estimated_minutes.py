"""drop homework estimated_minutes

Revision ID: 0002_drop_estimated_minutes
Revises: 0001_initial
Create Date: 2026-09-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_drop_estimated_minutes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("homeworks", "estimated_minutes")


def downgrade() -> None:
    op.add_column(
        "homeworks",
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
    )
