"""per-group reminder time

Revision ID: 0009_group_reminder_time
Revises: 0008_ci_group_subject_names
Create Date: 2026-09-21

Староста может задать время вечернего напоминания для своей группы
(в колонке groups.reminder_time). NULL означает «по умолчанию» —
значение REMINDER_TIME из настроек бота.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_group_reminder_time"
down_revision: str | None = "0008_ci_group_subject_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("reminder_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("groups", "reminder_time")
