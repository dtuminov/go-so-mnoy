#!/usr/bin/env bash
# Публикует все pending_review активности (события и заявки «ищу компанию»).
# После унификации (миграция 007) обе сущности живут в таблице `activities`,
# тип различает колонка `kind` ('event' | 'seeking').
#
# Использование:
#   ./scripts/approve_all.sh                  # обе ленты
#   ./scripts/approve_all.sh --events-only    # только kind='event'
#   ./scripts/approve_all.sh --seekings-only  # только kind='seeking'
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Определяем имя контейнера Postgres (первый, что запущен с нашим образом)
CONTAINER=$(docker ps --filter "name=postgres" --filter "ancestor=postgres:16" --format "{{.Names}}" | head -1)
if [[ -z "$CONTAINER" ]]; then
  # Fallback: ищем по имени проекта
  CONTAINER=$(docker ps --filter "name=go-so-mnoy" --format "{{.Names}}" | grep postgres | head -1)
fi
if [[ -z "$CONTAINER" ]]; then
  echo "approve_all.sh: не найден запущенный контейнер Postgres." >&2
  echo "Подними базу: docker compose up -d" >&2
  exit 1
fi

PSQL="docker exec -i $CONTAINER psql -U go_so_mnoy -d go_so_mnoy"

MODE="${1:-}"

run_sql() {
  echo "$1" | $PSQL
}

approve_kind() {
  local kind="$1"
  local label="$2"
  local time_col="$3"
  echo "==> Публикуем $label (pending_review → published):"
  run_sql "
    UPDATE activities
    SET status = 'published'
    WHERE status = 'pending_review' AND kind = '$kind';
    SELECT id, title, status, $time_col
    FROM activities
    WHERE kind = '$kind'
    ORDER BY id DESC
    LIMIT 20;
  "
}

approve_events()   { approve_kind "event"   "события"               "starts_at"; }
approve_seekings() { approve_kind "seeking" "заявки «ищу компанию»" "expires_at"; }

case "$MODE" in
  --events-only)
    approve_events
    ;;
  --seekings-only)
    approve_seekings
    ;;
  *)
    approve_events
    approve_seekings
    ;;
esac
