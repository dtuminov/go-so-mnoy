#!/usr/bin/env bash
# Перезапуск бота: гасит экземпляры этого репо (по cwd), миграции Alembic, старт через .venv.
# Запускай откуда угодно: ./restart.sh -t или bash /полный/путь/go-so-mnoy/restart.sh -t
#
# ВАЖНО: без --test/-t скрипт НЕ запустится — прод крутится на сервере,
# локально запускаем только тестового бота. Админ-бот локально не стартует
# (он один, живёт на сервере), для теста апрувь через: ./scripts/approve_all.sh
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
  echo "  --test | -t     — тестовый бот (.env.test, без admin_bot)" >&2
  echo "  --bg | -b       — запуск в фоне (лог: bot.log)" >&2
  echo "  --skip-migrate  — не вызывать alembic" >&2
  echo "  --prod          — запуск прод-бота + admin_bot (ТОЛЬКО на сервере!)" >&2
  echo "  --help | -h     — эта справка" >&2
}

SKIP_MIGRATE=0
RUN_BG=0
USE_TEST=0
FORCE_PROD=0
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
    --test|-t)
      USE_TEST=1
      ;;
    --prod)
      FORCE_PROD=1
      ;;
    *)
      echo "restart.sh: неизвестный аргумент: $arg" >&2
      usage
      exit 1
      ;;
  esac
done

# Защита: без флагов — не запускаем
if [[ "$USE_TEST" -eq 0 && "$FORCE_PROD" -eq 0 ]]; then
  echo "restart.sh: ❌ Укажи режим:" >&2
  echo "  ./restart.sh -t       — тестовый бот (локальная разработка)" >&2
  echo "  ./restart.sh --prod   — прод (только на сервере!)" >&2
  exit 1
fi

if [[ "$USE_TEST" -eq 1 ]]; then
  export ENV_FILE="${ROOT}/.env.test"
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "restart.sh: нет ${ENV_FILE}" >&2
    exit 1
  fi
  echo "restart.sh: 🧪 тестовый режим ($ENV_FILE)"
fi

# PID-ы процессов с командной строкой «python -m bot» или «python -m admin_bot»,
# cwd = корень этого проекта
list_repo_bot_pids() {
  local pid cwd
  for pid in $(pgrep -f "[Pp]ython.* -m (bot|admin_bot)" 2>/dev/null || true); do
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

# ── Тестовый режим: только основной бот, без admin_bot ──
if [[ "$USE_TEST" -eq 1 ]]; then
  if [[ "$RUN_BG" -eq 1 ]]; then
    BOT_LOG="${ROOT}/bot.log"
    echo "restart.sh: 🧪 тест-бот в фоне (лог: $BOT_LOG)"
    nohup "$VENV_PY" -m bot >>"$BOT_LOG" 2>&1 &
    echo "bot PID: $!"
  else
    echo "restart.sh: 🧪 тест-бот foreground (Ctrl+C — стоп)"
    exec "$VENV_PY" -m bot
  fi
  exit 0
fi

# ── Прод: оба бота ──
if [[ "$RUN_BG" -eq 1 ]]; then
  BOT_LOG="${ROOT}/bot.log"
  ADMIN_LOG="${ROOT}/admin_bot.log"
  echo "restart.sh: запуск в фоне"
  nohup "$VENV_PY" -m bot >>"$BOT_LOG" 2>&1 &
  echo "bot PID: $! (лог: $BOT_LOG)"
  nohup "$VENV_PY" -m admin_bot >>"$ADMIN_LOG" 2>&1 &
  echo "admin_bot PID: $! (лог: $ADMIN_LOG)"
else
  echo "restart.sh: foreground — оба бота (Ctrl+C — стоп)"
  "$VENV_PY" -m admin_bot &
  ADMIN_PID=$!
  trap 'kill $ADMIN_PID 2>/dev/null; wait $ADMIN_PID 2>/dev/null' EXIT
  exec "$VENV_PY" -m bot
fi
