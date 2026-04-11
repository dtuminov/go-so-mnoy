#!/usr/bin/env bash
# Перезапуск бота: гасит экземпляры этого репо (по cwd), миграции Alembic, старт через .venv.
# Запускай откуда угодно: ./restart.sh или bash /полный/путь/go-so-mnoy/restart.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV_PY="${ROOT}/.venv/bin/python"
ALEMBIC="${ROOT}/.venv/bin/alembic"
if [[ ! -x "$VENV_PY" ]]; then
  echo "restart.sh: нет ${VENV_PY}" >&2
  echo "Создай окружение: python3 -m venv .venv && source .venv/bin/activate && pip install -e ." >&2
  exit 1
fi

usage() {
  echo "Использование: $0 [опции]" >&2
  echo "  (без опций)     — стоп ботов этого репо → alembic upgrade head → бот в foreground" >&2
  echo "  --bg | -b       — то же, бот в фоне (лог: ${ROOT}/bot.log)" >&2
  echo "  --skip-migrate  — не вызывать alembic (если БД недоступна и нужен только стоп)" >&2
  echo "  --help | -h     — эта справка" >&2
  echo "" >&2
  echo "Нужен .env с DATABASE_URL (Postgres), иначе alembic упадёт — подними docker compose." >&2
}

SKIP_MIGRATE=0
RUN_BG=0
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    --skip-migrate)
      SKIP_MIGRATE=1
      ;;
    --bg|-b)
      RUN_BG=1
      ;;
    *)
      echo "restart.sh: неизвестный аргумент: $arg" >&2
      usage
      exit 1
      ;;
  esac
done

# PID-ы процессов с командной строкой «python -m bot», cwd = корень этого проекта
list_repo_bot_pids() {
  local pid cwd
  for pid in $(pgrep -f "[Pp]ython.* -m bot" 2>/dev/null || true); do
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
    if [[ "$cwd" == "$ROOT" ]]; then
      echo "$pid"
    fi
  done
}

collect_pids_space_sep() {
  local pid acc=""
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    acc="${acc}${acc:+ }$pid"
  done < <(list_repo_bot_pids)
  echo "$acc"
}

stop_bots() {
  local pids pid
  pids="$(collect_pids_space_sep)"
  if [[ -z "$pids" ]]; then
    echo "restart.sh: процессов «python -m bot» с cwd=$ROOT не найдено"
    return 0
  fi
  echo "restart.sh: останавливаю PID: $pids"
  for pid in $pids; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in $(collect_pids_space_sep); do
    [[ -z "${pid:-}" ]] && continue
    kill -KILL "$pid" 2>/dev/null || true
  done
  sleep 0.3
}

stop_bots

if [[ "$SKIP_MIGRATE" -eq 0 ]]; then
  if [[ ! -x "$ALEMBIC" ]]; then
    echo "restart.sh: нет ${ALEMBIC}" >&2
    exit 1
  fi
  echo "restart.sh: alembic upgrade head"
  "$ALEMBIC" upgrade head
else
  echo "restart.sh: пропуск миграций (--skip-migrate)"
fi

if [[ "$RUN_BG" -eq 1 ]]; then
  LOG="${ROOT}/bot.log"
  echo "restart.sh: запуск в фоне, лог: $LOG"
  nohup "$VENV_PY" -m bot >>"$LOG" 2>&1 &
  echo "PID: $!"
else
  echo "restart.sh: foreground (Ctrl+C — стоп). Фон: $0 --bg"
  exec "$VENV_PY" -m bot
fi
