# Структура репозитория

Актуальное описание каталогов и назначения файлов. **Обновляй этот файл** при добавлении или удалении значимых путей.

## Зафиксированный стек (MVP)

| Компонент | Технология |
|-----------|------------|
| Бот | Python **3.12+**, **aiogram 3**, FSM в **MemoryStorage** (для проды позже Redis) |
| БД | **PostgreSQL** |
| Миграции | **Alembic** (обычно в связке с **SQLAlchemy 2 async** + **asyncpg**) |

Стек, локальная БД и команды — в **`CLAUDE.md`** (разделы **Tech Stack**, **Essential Commands**).

## Первый запуск

1. Python **3.12+**, виртуальное окружение и **`pip install -e .`** из корня репозитория.
2. Файл **`.env`** по образцу **`.env.example`**: обязательно непустые **`BOT_TOKEN`** и **`DATABASE_URL`** (`postgresql+asyncpg://…`). Опционально **`BOT_USERNAME`** (без `@`) для deep link из канала.
3. Поднять PostgreSQL: **`docker compose up -d`** (или свой инстанс). Если порт **5432** занят другим Postgres — останови тот сервис или поменяй проброс в `docker-compose.yml` (например `5433:5432`) и поправь `DATABASE_URL`.
4. **`alembic upgrade head`**
5. **`python -m bot`**

По желанию позже: **ruff**, **mypy** / **pyright**, **pre-commit**, **Redis** для FSM при нескольких воркерах.

**Лента событий:** в БД новые события со статусом `pending_review`; в боте в «📍 Найти событие» показываются только **`published`**. Ручная публикация через SQL — **`README.md`** (модерация).

## Корень

| Путь | Назначение |
|------|------------|
| `README.md` | Запуск, модерация событий через `psql` / SQL |
| `consept.md` | Продукт: видение, MVP, GTM, метрики |
| `bot.md` | Telegram-бот: сценарии и функции |
| `chennel.md` | Telegram-канал: контент и связка с ботом |
| `CLAUDE.md` | Контекст для AI: продукт, стек, команды, правила (без «мета» про другие репозитории) |
| `STRUCTURE.md` | Этот файл — карта репозитория |
| `.env.example` | Шаблон `.env`: токен, URL PostgreSQL, опционально `BOT_USERNAME` (плейсхолдер под deep link) |
| `.gitignore` | Игноры для артефактов и секретов |
| `.cursor/rules/` | Правила Cursor (агентный workflow) |
| `.cursor/commands/` | Slash-команды Cursor (`validate`, `commit`) |
| `.claude/skills/` | Навыки Claude Code / агентов (композиция React, UI guidelines) |
| `docs/plans/` | Черновики планов реализации (пустой каталог с `.gitkeep` до первых файлов) |
| `docs/architecture/domain-model.md` | UML домена (Mermaid) + ссылка на PlantUML |
| `docs/architecture/domain-model.puml` | Тот же домен в **PlantUML** для [PlantText](https://www.planttext.com) |
| `pyproject.toml` | Зависимости и метаданные пакета (editable install) |
| `docker-compose.yml` | Локальный **PostgreSQL 16** (user/db/password `go_so_mnoy`) |
| `alembic.ini` | Конфиг Alembic |
| `.cursor/worktrees.json` | Подсказка для worktree: `pip install -e .` |

## Код

| Путь | Назначение |
|------|------------|
| `bot/` | Пакет бота: `python -m bot` |
| `bot/__main__.py` | Точка входа CLI |
| `bot/main.py` | `Dispatcher`, `MemoryStorage`, middleware сессии БД, polling |
| `bot/config.py` | `pydantic-settings`: `BOT_TOKEN`, `DATABASE_URL`, опционально `BOT_USERNAME` |
| `bot/constants.py` | ID Москвы, строковые статусы сущностей |
| `bot/db/` | `Base`, фабрика сессий, `get_sessionmaker()` |
| `bot/middlewares/` | `DbSessionMiddleware` — сессия и commit на апдейт |
| `bot/models/` | `User`, `City`, `Event`, `EventParticipant`, `CompanySeeking`, `CompanySeekingResponse` |
| `bot/services/` | `users`, `events` — upsert пользователя, список/создание/запись на событие |
| `bot/keyboards/` | Reply-меню главного экрана |
| `bot/utils/` | форматирование дат (МСК), разбор даты в FSM |
| `bot/handlers/` | `common` (`/start`, `/help`, deep link `event_` / `seek_`), `menu`, `events` (callback `e:` / `j:`), `create_event` (FSM, `/cancel`) |
| `alembic/` | Миграции: `env.py`, `versions/` |
| `alembic/versions/001_initial_users.py` | Таблица `users` |
| `alembic/versions/002_domain_core.py` | `cities` (+ Москва), события, участники, «ищу компанию», поля профиля `users` |
