"""add users.selected_group_id

Revision ID: 0003_add_user_selected_group
Revises: 0002_drop_estimated_minutes
Create Date: 2026-09-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_user_selected_group"
down_revision: str | None = "0002_drop_estimated_minutes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("selected_group_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "selected_group_id")
