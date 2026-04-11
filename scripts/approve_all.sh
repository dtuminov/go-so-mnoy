#!/usr/bin/env bash
# Публикует все pending_review события и заявки «ищу компанию».
# Использование: ./scripts/approve_all.sh [--events-only | --seekings-only]
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

approve_events() {
  echo "==> Публикуем события (pending_review → published):"
  run_sql "
    UPDATE events
    SET status = 'published'
    WHERE status = 'pending_review';
    SELECT id, title, status, starts_at
    FROM events
    ORDER BY id DESC
    LIMIT 20;
  "
}

approve_seekings() {
  echo "==> Публикуем заявки «ищу компанию» (pending_review → published):"
  run_sql "
    UPDATE company_seekings
    SET status = 'published'
    WHERE status = 'pending_review';
    SELECT id, title, status, expires_at
    FROM company_seekings
    ORDER BY id DESC
    LIMIT 20;
  "
}

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
