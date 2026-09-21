"""Перенос данных из SQLite в PostgreSQL с приведением целостности.

Использование:
    python scripts/migrate_sqlite_to_postgres.py \
        --src sqlite+aiosqlite:///homework.db \
        --dst postgresql+asyncpg://postgres:postgres@localhost:5432/homework_bot

Сначала запусти alembic upgrade head на целевой БД.
Сиротные записи (несуществующие FK) пропускаются и выпиваются в лог.
id сохраняются 1:1, последовательности (sequences) обновляются.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.models import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _aware(value):
    if value is None:
        return None
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=UTC)
    return value


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default="sqlite+aiosqlite:///homework.db")
    parser.add_argument(
        "--dst",
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/homework_bot",
    )
    args = parser.parse_args()

    src = create_async_engine(args.src)
    dst = create_async_engine(args.dst)

    async with src.begin() as conn:
        tables = {}
        for name in ("users", "groups", "group_members", "subjects",
                     "homeworks", "attachments", "homework_links"):
            rows = [
                dict(r._mapping)
                for r in (await conn.execute(text(f"SELECT * FROM {name} ORDER BY id")))
            ]
            tables[name] = rows
            print(f"{name}: {len(rows)} строк")

    valid_user_ids = {r["id"] for r in tables["users"]}
    valid_group_ids = {r["id"] for r in tables["groups"]}

    kept: dict[str, list[dict]] = {k: [] for k in tables}
    kept["users"] = tables["users"]
    kept["groups"] = tables["groups"]

    for r in tables["group_members"]:
        if r["user_id"] in valid_user_ids and r["group_id"] in valid_group_ids:
            kept["group_members"].append(r)
        else:
            print(f"  отброшено group_members id={r['id']} (нет FK)")

    subjects_by_id = {}
    for r in tables["subjects"]:
        if r["group_id"] in valid_group_ids:
            kept["subjects"].append(r)
            subjects_by_id[r["id"]] = r
        else:
            print(f"  отброшено subject id={r['id']} (нет группы)")

    valid_subject_ids = set(subjects_by_id)
    valid_homework_ids = set()
    for r in tables["homeworks"]:
        if (
            r["group_id"] in valid_group_ids
            and r["subject_id"] in valid_subject_ids
            and r["author_id"] in valid_user_ids
        ):
            kept["homeworks"].append(r)
            valid_homework_ids.add(r["id"])
        else:
            print(f"  отброшено homework id={r['id']} (нет FK)")

    for name, fk_col in (("attachments", "homework_id"), ("homework_links", "homework_id")):
        for r in tables[name]:
            if r[fk_col] in valid_homework_ids:
                kept[name].append(r)
            else:
                print(f"  отброшено {name} id={r['id']} (нет FK)")

    timestamptz_cols = {
        "users": {"created_at", "updated_at"},
        "groups": {"created_at", "updated_at", "invite_code_expires_at"},
        "group_members": {"joined_at"},
        "subjects": {"created_at"},
        "homeworks": {"created_at", "updated_at"},
        "attachments": {"created_at"},
        "homework_links": {"created_at"},
    }

    order = [
        "users", "groups", "group_members", "subjects", "homeworks",
        "attachments", "homework_links",
    ]

    date_cols = {
        "homeworks": {"deadline"},
    }

    async with dst.begin() as conn:
        for name in reversed(order):
            await conn.execute(text(f'TRUNCATE TABLE "{name}" CASCADE'))
        selected_map: dict[int, int | None] = {}
        for name in order:
            rows = kept[name]
            if not rows:
                continue
            table = Base.metadata.tables[name]
            for r in rows:
                if name in timestamptz_cols:
                    for col in timestamptz_cols[name]:
                        if col in r:
                            r[col] = _aware(r[col])
            for r in rows:
                if name in date_cols:
                    for col in date_cols[name]:
                        if col in r and isinstance(r[col], str):
                            r[col] = datetime.fromisoformat(r[col]).date()
            if name == "users":
                # groups ссылаются на users (created_by), users на groups
                # (selected_group_id) — круговая зависимость. Вставляем users
                # без selected_group_id, связь доставим после groups.
                selected_map = {r["id"]: r["selected_group_id"] for r in rows}
                for r in rows:
                    r["selected_group_id"] = None
            await conn.execute(table.insert(), rows)
            print(f"  записано в postgres: {name} — {len(rows)}")

        # восстанавливаем selected_group_id (NULL, если группы нет)
        group_ids = {r["id"] for r in kept["groups"]}
        for uid, sel in selected_map.items():
            if sel is not None and sel in group_ids:
                await conn.execute(
                    text("UPDATE users SET selected_group_id = :sel WHERE id = :uid"),
                    {"sel": sel, "uid": uid},
                )

        # синхронизация sequence
        for name in order:
            row = await conn.execute(
                text(
                    f"SELECT MAX(id) FROM {name}"
                )
            )
            max_id = row.scalar()
            if max_id:
                await conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), :v)"
                    ),
                    {"v": max_id},
                )

    await src.dispose()
    await dst.dispose()
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
