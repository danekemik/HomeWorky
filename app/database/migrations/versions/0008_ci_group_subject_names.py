"""case-insensitive uniqueness for group and subject names

Revision ID: 0008_ci_group_subject_names
Revises: 0007_unique_hw_subject_date
Create Date: 2026-09-21

Названия групп и предметов сравниваются без учёта регистра. Перед
наложением функциональных unique-индексов case-variant дубликаты
схлопываются: участники, предметы и задания переносятся на самую
раннюю запись, остальные копии удаляются. Индексы создаются только
в PostgreSQL: SQLite не поддерживает пользовательские функции в
индексных выражениях, поэтому там уникальность обеспечивается
прикладной проверкой (см. GroupRepository.name_exists).
"""
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_ci_group_subject_names"
down_revision: str | None = "0007_unique_hw_subject_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _expanding(statement: str) -> sa.TextClause:
    return sa.text(statement).bindparams(sa.bindparam("drops", expanding=True))


def _deduplicate_groups(bind: sa.Connection) -> None:
    rows = bind.execute(sa.text("SELECT id, name FROM groups ORDER BY id")).all()
    buckets: dict[str, list[int]] = defaultdict(list)
    for group_id, name in rows:
        buckets[name.lower()].append(group_id)
    for ids in buckets.values():
        if len(ids) < 2:
            continue
        keep, drops = ids[0], ids[1:]
        for drop in drops:
            bind.execute(
                sa.text(
                    "INSERT INTO group_members (user_id, group_id, role, joined_at) "
                    "SELECT gm.user_id, :keep, gm.role, gm.joined_at "
                    "FROM group_members AS gm "
                    "WHERE gm.group_id = :drop AND NOT EXISTS ("
                    "  SELECT 1 FROM group_members AS t "
                    "  WHERE t.group_id = :keep AND t.user_id = gm.user_id)"
                ),
                {"keep": keep, "drop": drop},
            )
        bind.execute(
            sa.text(
                "UPDATE group_members AS t SET role = 'ADMIN' "
                "WHERE t.group_id = :keep AND t.role <> 'ADMIN' AND EXISTS ("
                "  SELECT 1 FROM group_members AS gm "
                "  WHERE gm.group_id IN :drops AND gm.user_id = t.user_id "
                "    AND gm.role = 'ADMIN')"
            ).bindparams(sa.bindparam("drops", expanding=True)),
            {"keep": keep, "drops": drops},
        )
        bind.execute(
            sa.text("DELETE FROM group_members WHERE group_id IN :drops").bindparams(
                sa.bindparam("drops", expanding=True)
            ),
            {"drops": drops},
        )
        for table, column in (
            ("subjects", "group_id"),
            ("homeworks", "group_id"),
            ("users", "selected_group_id"),
        ):
            bind.execute(
                _expanding(f"UPDATE {table} SET {column} = :keep WHERE {column} IN :drops"),
                {"keep": keep, "drops": drops},
            )
        bind.execute(
            sa.text("DELETE FROM groups WHERE id IN :drops").bindparams(
                sa.bindparam("drops", expanding=True)
            ),
            {"drops": drops},
        )


def _deduplicate_subjects(bind: sa.Connection) -> None:
    rows = bind.execute(
        sa.text("SELECT id, group_id, name FROM subjects ORDER BY id")
    ).all()
    buckets: dict[tuple[int, str], list[int]] = defaultdict(list)
    for subject_id, group_id, name in rows:
        buckets[(group_id, name.lower())].append(subject_id)
    for ids in buckets.values():
        if len(ids) < 2:
            continue
        keep, drops = ids[0], ids[1:]
        for drop in drops:
            homeworks = bind.execute(
                sa.text("SELECT id, deadline FROM homeworks WHERE subject_id = :drop"),
                {"drop": drop},
            ).all()
            for homework_id, deadline in homeworks:
                existing = bind.execute(
                    sa.text(
                        "SELECT id FROM homeworks "
                        "WHERE subject_id = :keep AND deadline = :deadline"
                    ),
                    {"keep": keep, "deadline": deadline},
                ).scalar()
                if existing is None:
                    bind.execute(
                        sa.text(
                            "UPDATE homeworks SET subject_id = :keep WHERE id = :hw"
                        ),
                        {"keep": keep, "hw": homework_id},
                    )
                    continue
                for table in ("attachments", "homework_links"):
                    bind.execute(
                        sa.text(
                            f"UPDATE {table} SET homework_id = :existing "
                            "WHERE homework_id = :hw"
                        ),
                        {"existing": existing, "hw": homework_id},
                    )
                bind.execute(
                    sa.text("DELETE FROM homeworks WHERE id = :hw"),
                    {"hw": homework_id},
                )
        bind.execute(
            sa.text("DELETE FROM subjects WHERE id IN :drops").bindparams(
                sa.bindparam("drops", expanding=True)
            ),
            {"drops": drops},
        )


def upgrade() -> None:
    bind = op.get_bind()
    _deduplicate_groups(bind)
    _deduplicate_subjects(bind)
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_groups_name_lower "
            "ON groups (LOWER(name))"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_subjects_group_name_lower "
            "ON subjects (group_id, LOWER(name))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_subjects_group_name_lower")
        op.execute("DROP INDEX IF EXISTS uq_groups_name_lower")
