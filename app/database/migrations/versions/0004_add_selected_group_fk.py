"""add FK + index on users.selected_group_id to match the model

Revision ID: 0004_add_selected_group_fk
Revises: 0003_add_user_selected_group
Create Date: 2026-09-21

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_selected_group_fk"
down_revision: str | None = "0003_add_user_selected_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.create_index(
                "ix_users_selected_group_id", ["selected_group_id"]
            )
            batch_op.create_foreign_key(
                "fk_users_selected_group_id_groups",
                "groups",
                ["selected_group_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_index(
            "ix_users_selected_group_id", "users", ["selected_group_id"]
        )
        op.create_foreign_key(
            "fk_users_selected_group_id_groups",
            "users",
            "groups",
            ["selected_group_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_constraint(
                "fk_users_selected_group_id_groups", type_="foreignkey"
            )
            batch_op.drop_index("ix_users_selected_group_id")
    else:
        op.drop_constraint(
            "fk_users_selected_group_id_groups", "users", type_="foreignkey"
        )
        op.drop_index("ix_users_selected_group_id", table_name="users")
