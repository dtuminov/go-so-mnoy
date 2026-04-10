# Структура репозитория

Актуальное описание каталогов и назначения файлов. **Обновляй этот файл** при добавлении или удалении значимых путей.

## Зафиксированный стек (MVP)

| Компонент | Технология |
|-----------|------------|
| Бот | Python **3.12+**, **aiogram 3** |
| БД | **PostgreSQL** |
| Миграции | **Alembic** (обычно в связке с **SQLAlchemy 2 async** + **asyncpg**) |

Стек, локальная БД и команды — в **`CLAUDE.md`** (разделы **Tech Stack**, **Essential Commands**).

## Первый запуск

1. Python **3.12+**, виртуальное окружение и **`pip install -e .`** из корня репозитория.
2. Файл **`.env`** по образцу **`.env.example`** (`BOT_TOKEN`, `DATABASE_URL`).
3. Поднять PostgreSQL: **`docker compose up -d`** (или свой инстанс).
4. **`alembic upgrade head`**
5. **`python -m bot`**

По желанию позже: **ruff**, **mypy** / **pyright**, **pre-commit**, **Redis** для FSM при нескольких воркерах.

## Корень

| Путь | Назначение |
|------|------------|
| `README.md` | Краткое описание репозитория и команды для локального запуска |
| `consept.md` | Продукт: видение, MVP, GTM, метрики |
| `bot.md` | Telegram-бот: сценарии и функции |
| `chennel.md` | Telegram-канал: контент и связка с ботом |
| `CLAUDE.md` | Контекст для AI: продукт, стек, команды, правила (без «мета» про другие репозитории) |
| `STRUCTURE.md` | Этот файл — карта репозитория |
| `.env.example` | Шаблон `.env`: токен бота, URL PostgreSQL (без секретов) |
| `.gitignore` | Игноры для артефактов и секретов |
| `.cursor/rules/` | Правила Cursor (агентный workflow) |
| `.cursor/commands/` | Slash-команды Cursor (`validate`, `commit`) |
| `.claude/skills/` | Навыки Claude Code / агентов (композиция React, UI guidelines) |
| `docs/plans/` | Черновики планов реализации (пустой каталог с `.gitkeep` до первых файлов) |
| `pyproject.toml` | Зависимости и метаданные пакета (editable install) |
| `docker-compose.yml` | Локальный **PostgreSQL 16** (user/db/password `go_so_mnoy`) |
| `alembic.ini` | Конфиг Alembic |
| `.cursor/worktrees.json` | Подсказка для worktree: `pip install -e .` |

## Код

| Путь | Назначение |
|------|------------|
| `bot/` | Пакет бота: `python -m bot` |
| `bot/__main__.py` | Точка входа CLI |
| `bot/main.py` | `Dispatcher`, polling, init/dispose БД |
| `bot/config.py` | `pydantic-settings`: `BOT_TOKEN`, `DATABASE_URL` |
| `bot/db/` | `Base`, сессии SQLAlchemy async |
| `bot/models/` | ORM-модели (старт: `User`) |
| `bot/handlers/` | Роутеры aiogram (старт: `/start`) |
| `alembic/` | Миграции: `env.py`, `versions/` |
| `alembic/versions/001_initial_users.py` | Первая таблица `users` |
