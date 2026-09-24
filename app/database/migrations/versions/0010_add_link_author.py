"""add author to homework links

Revision ID: 0010_add_link_author
Revises: 0009_group_reminder_time
Create Date: 2026-09-24

У ссылок появляется автор (homework_links.author_id) — чтобы на карточке
«папки» рядом со ссылкой можно было показывать, кто её добавил.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_add_link_author"
down_revision: str | None = "0009_group_reminder_time"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("homework_links", sa.Column("author_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_homework_links_author_id"), "homework_links", ["author_id"]
    )
    op.create_foreign_key(
        "fk_homework_links_author_id_users",
        "homework_links",
        "users",
        ["author_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_homework_links_author_id_users", "homework_links", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_homework_links_author_id"), table_name="homework_links"
    )
    op.drop_column("homework_links", "author_id")
