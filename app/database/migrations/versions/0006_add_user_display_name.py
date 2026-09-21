"""add display_name to users

Revision ID: 0006_add_user_display_name
Revises: 0005_unique_invite_code
Create Date: 2026-09-21

Real имя пользователя, введённое при вступлении в группу
(показывается в «Кто добавил» вместо телеграм-ника).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_add_user_display_name"
down_revision: str | None = "0005_unique_invite_code"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("display_name", sa.String(64), nullable=True))
    else:
        op.add_column(
            "users", sa.Column("display_name", sa.String(64), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("display_name")
    else:
        op.drop_column("users", "display_name")
