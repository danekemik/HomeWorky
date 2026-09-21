# Бот для управления домашними заданиями

Telegram-бот для учебной группы: участники добавляют домашние задания
с дедлайнами и файлами, бот присылает напоминания и помогает не забывать,
что сдавать завтра.

## Возможности

- ➕ Добавление домашних заданий: предмет (создаётся на лету), название,
  описание, дата сдачи (календарь), файлы (до 3 шт.) и ссылки.
- 🗂 Просмотр заданий: «Ближайшие дедлайны» (сегодня/завтра), «Все задания»
  по категориям — прошедшие, актуальные, созданные мной (с пагинацией).
- 📎 При открытии карточки задания бот сам присылает прикреплённые
  файлы и фото.
- ✏️ Редактирование и удаление только своих заданий
  (староста группы может менять любые).
- 🎛 Управление группой для старосты: список участников с удалением,
  переименование группы и перевыпуск инвайт-кода.
- 📊 Статистика по группе.
- 🔔 Ежедневное вечернее напоминание о дедлайнах на завтра
  (по умолчанию в 20:00, время в `REMINDER_TIME`).
- Работа и в групповом чате, и в личке: доступ к группам проверяется
  серверно через Telegram API.

## Стек

Python 3.12+, aiogram 3, SQLAlchemy 2 (async), Alembic, PostgreSQL,
Docker Compose. В тестах — SQLite.

## Локальный запуск

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env   # впишите BOT_TOKEN от @BotFather
alembic upgrade head
python -m app.main
```

Если в `.env` указан `REDIS_URL` — состояния FSM хранятся в Redis,
иначе используется MemoryStorage (логика: `app/bot/main.py::create_storage`).

## Запуск в Docker

```bash
cp .env.example .env
# впишите BOT_TOKEN (и при необходимости POSTGRES_PASSWORD)
docker compose up -d --build
```

Стек поднимает три сервиса: `db` (Postgres 16), `redis` (FSM),
`bot` (Entrypoint накатывает `alembic upgrade head` и запускает поллинг).
Порт Postgres наружу проброшен на `127.0.0.1:5433` (Redis — на
`127.0.0.1:6380`), чтобы не конфликтовать с локальными сервисами на VPS.

Локальные контейнеры (только db и redis) для разработки:

```bash
docker compose up -d db redis
```

## Деплой на VPS

```bash
git clone <repo> && cd <repo>
cp .env.example .env          # BOT_TOKEN, REMINDER_TIME и др.
docker compose up -d --build
docker compose logs -f bot    # убедиться, что бот запустился
```

Перенос существующих данных из SQLite в Postgres (перед первым запуском):

```bash
alembic upgrade head            # создать схему в Postgres
python scripts/migrate_sqlite_to_postgres.py --src sqlite+aiosqlite:///homework.db \
    --dst postgresql+asyncpg://postgres:postgres@<host>/homework_bot
```

## Бэкапы

```bash
./scripts/backup_pg.sh [N_DAYS_KEEP]   # дамп в ./backups с ротацией
```

Пример cron (ежедневно в 03:00):

```
0 3 * * * /path/to/project/scripts/backup_pg.sh >> /path/to/project/logs/backup.log 2>&1
```

## Использование

1. Добавьте бота в свою группу, дайте права администратора
   (нужно для проверки участников).
2. Напишите в группе `/start` — бот запомнит вас участником.
3. В личке с ботом откройте меню `/menu` и выберите свою группу.
4. Добавляйте задания, следите за дедлайнами, делись файлами.

## Команды

- `/start`, `/help` — приветствие и помощь
- `/menu` — главное меню
- `/stats` — статистика (в личке)

## Структура

```
app/
  bot/         — aiogram: роутеры, клавиатуры, FSM, middlewares, filters
  database/    — модели, репозитории, Alembic-миграции
  services/    — бизнес-логика (homework, group, notification)
  scheduler.py — фоновое напоминание о дедлайнах
  config.py    — настройки (pydantic-settings)
  dates.py     — русские названия месяцев (общий формат дат)
  main.py      — точка входа
tests/         — pytest (SQLite, в памяти)
```

## Проверки

```bash
ruff check .
mypy app tests
pytest -q
```