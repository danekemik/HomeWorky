#!/usr/bin/env bash
set -euo pipefail

# Бэкап Postgres-базы hw-бота в дамп с ротацией.
# Использование:  ./scripts/backup_pg.sh [N_DAYS_TO_KEEP]
# Кнопка cron:     0 3 * * * /path/to/project/scripts/backup_pg.sh >> /path/to/project/logs/backup.log 2>&1

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
KEEP_DAYS="${1:-30}"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

# Составляем строку подключения из .env, если она задана целиком.
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  PGURL="${DATABASE_URL/asyncpg/}"  # postgresql+asyncpg:// -> postgresql://
fi

if command -v pg_dump >/dev/null 2>&1; then
  if [[ -n "${PGURL:-}" ]]; then
    pg_dump --no-owner --no-privileges --format=custom "$PGURL" \
        > "$BACKUP_DIR/homework_$STAMP.dump"
  else
    echo "Нет DATABASE_URL и нет локального pg_dump." >&2
    exit 1
  fi
else
  # Локального клиента нет — дампим через образ postgres (docker compose).
  docker compose exec -T db pg_dump -U postgres --no-owner --no-privileges --format=custom \
      homework_bot > "$BACKUP_DIR/homework_$STAMP.dump"
fi

# Ротация старых дампов.
find "$BACKUP_DIR" -name 'homework_*.dump' -mtime "+$KEEP_DAYS" -delete

echo "Бэкап сохранён: $BACKUP_DIR/homework_$STAMP.dump"