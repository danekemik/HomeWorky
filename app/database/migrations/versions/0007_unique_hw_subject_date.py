"""enforce unique homework per subject+deadline; add author_id to attachments

Revision ID: 0007_unique_hw_subject_date
Revises: 0006_add_user_display_name
Create Date: 2026-09-21

На одном предмете может быть только одно ДЗ на дату. Перед
наложением ограничения дубликаты схлопываются: вложения и ссылки
переносятся на самую свежую карточку дублирующей группы, остальные
копии удаляются. В Attachment добавляется автор файла.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_unique_hw_subject_date"
down_revision: str | None = "0006_add_user_display_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _deduplicate_homeworks() -> None:
    """Схлопывает дубликаты (group_id, subject_id, deadline) в одну карточку."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT group_id, subject_id, deadline FROM homeworks "
            "GROUP BY group_id, subject_id, deadline HAVING COUNT(*) > 1"
        )
    ).all()
    for group_id, subject_id, deadline in rows:
        candidates = bind.execute(
            sa.text(
                "SELECT id FROM homeworks "
                "WHERE group_id = :g AND subject_id = :s AND deadline = :d "
                "ORDER BY id"
            ),
            {"g": group_id, "s": subject_id, "d": deadline},
        ).all()
        keep_id = candidates[-1][0]
        drop_ids = [row[0] for row in candidates[:-1]]
        for table in ("attachments", "homework_links"):
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET homework_id = :keep "
                    "WHERE homework_id IN :drop"
                ).bindparams(sa.bindparam("drop", expanding=True)),
                {"keep": keep_id, "drop": drop_ids},
            )
        bind.execute(
            sa.text(
                "DELETE FROM homeworks WHERE id IN :drop"
            ).bindparams(sa.bindparam("drop", expanding=True)),
            {"drop": drop_ids},
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("attachments") as batch_op:
            batch_op.add_column(sa.Column("author_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_attachments_author_id_users", "users", ["author_id"], ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index(
                "ix_attachments_author_id", ["author_id"], unique=False
            )
    else:
        op.add_column(
            "attachments", sa.Column("author_id", sa.Integer(), nullable=True)
        )
        op.create_foreign_key(
            "fk_attachments_author_id_users",
            "attachments",
            "users",
            ["author_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_attachments_author_id", "attachments", ["author_id"], unique=False
        )

    _deduplicate_homeworks()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("homeworks") as batch_op:
            batch_op.create_unique_constraint(
                "uq_homework_group_subject_deadline",
                ["group_id", "subject_id", "deadline"],
            )
    else:
        op.create_unique_constraint(
            "uq_homework_group_subject_deadline",
            "homeworks",
            ["group_id", "subject_id", "deadline"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("homeworks") as batch_op:
            batch_op.drop_constraint(
                "uq_homework_group_subject_deadline", type_="unique"
            )
        with op.batch_alter_table("attachments") as batch_op:
            batch_op.drop_index("ix_attachments_author_id")
            batch_op.drop_constraint("fk_attachments_author_id_users", type_="foreignkey")
            batch_op.drop_column("author_id")
    else:
        op.drop_constraint(
            "uq_homework_group_subject_deadline",
            "homeworks",
            type_="unique",
        )
        op.drop_index("ix_attachments_author_id", table_name="attachments")
        op.drop_constraint("fk_attachments_author_id_users", "attachments", type_="foreignkey")
        op.drop_column("attachments", "author_id")
