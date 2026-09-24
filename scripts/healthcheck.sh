#!/usr/bin/env bash
set -euo pipefail

# Проверка здоровья стека бота и алерты в Telegram автору.
# Использование:
#   ./scripts/healthcheck.sh            # проверить и уведомить при проблемах
#   ./scripts/healthcheck.sh --test     # отправить тестовое сообщение в ALERT_CHAT_ID
# Кнопка cron (каждые 5 минут):
#   */5 * * * * cd /opt/homework-bot && ./scripts/healthcheck.sh  2>> /opt/homework-bot/logs/healthcheck.log

cd "$(dirname "$0")/.."

COMPOSE_PROJECT="homework-bot"
SERVICES="bot db redis"
STATE_FILE="${STATE_FILE:-logs/.healthcheck_state}"
COMPOSE_FLAGS=(-f docker-compose.yml -f docker-compose.prod.yml --project-directory "$(pwd)")

# Собираем BOT_TOKEN и ALERT_CHAT_ID из .env.
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

notify() { # $1 — текст
  local text="$1"
  if [[ -z "${BOT_TOKEN:-}" || -z "${ALERT_CHAT_ID:-}" ]]; then
    echo "Пропуск уведомления: нет BOT_TOKEN или ALERT_CHAT_ID" >&2
    return 0
  fi
  curl -fsS --max-time 10 -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="${ALERT_CHAT_ID}" -d text="${text}" -d disable_notification=false >/dev/null || echo "Не удалось отправить уведомление" >&2
}

if [[ "${1:-}" == "--test" ]]; then
  notify "✅ Тестовый алерт healthcheck: бот Homy на связи (ʘ‿‿ʘ)"
  exit 0
fi

mkdir -p "$(dirname "$STATE_FILE")"

status_of() { # $1 = имя сервиса -> статус или DOWN
  local svc="$1"
  local cid
  cid="$(docker compose "${COMPOSE_FLAGS[@]}" -p "$COMPOSE_PROJECT" ps -q "$svc" 2>/dev/null || true)"
  [[ -z "${cid}" ]] && echo "DOWN" && return
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo "DOWN"
}

fail_lines=""
for svc in $SERVICES; do
  st="$(status_of "$svc")"
  case "$st" in
    running|healthy) : ;;            # ок
    *) fail_lines="${fail_lines}❌ ${svc}: ${st}"$'\n' ;;
  esac
done

was_down="$(cat "$STATE_FILE" 2>/dev/null || true)"

if [[ -n "$fail_lines" ]]; then
  if [[ "$was_down" == "no" ]]; then
    notify "🚨 Homy лежит!
${fail_lines}Проверь VPS: docker compose ps" || true
  fi
  echo "down" > "$STATE_FILE"
  exit 1
else
  if [[ "$was_down" == "down" ]]; then
    notify "✅ Homy снова в строю — все сервисы (bot/db/redis) в норме." || true
  fi
  echo "no" > "$STATE_FILE"
  exit 0
fi