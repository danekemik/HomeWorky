"""enforce unique invite_code

Revision ID: 0005_unique_invite_code
Revises: 0004_add_selected_group_fk
Create Date: 2026-09-21

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_unique_invite_code"
down_revision: str | None = "0004_add_selected_group_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("groups") as batch_op:
            batch_op.create_index("ix_groups_invite_code", ["invite_code"], unique=True)
    else:
        op.create_index(
            "ix_groups_invite_code", "groups", ["invite_code"], unique=True
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("groups") as batch_op:
            batch_op.drop_index("ix_groups_invite_code")
    else:
        op.drop_index("ix_groups_invite_code", table_name="groups")
