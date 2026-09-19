#!/usr/bin/env sh
set -e

echo "Запуск миграций..."
alembic upgrade head

echo "Запуск бота..."
exec python -m app.main