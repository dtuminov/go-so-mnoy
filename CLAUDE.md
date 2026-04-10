# CLAUDE.md

## What Is This Project

Pet project: **канал + Telegram-бот** как MVP для гипотезы «куда пойти сегодня и с кем». Канал — витрина и привычка; бот — действие (найти событие, компанию, создать событие, присоединиться). Долгосрочно задумано как приложение (см. продуктовую документацию).

## Product Docs (read before feature work)

| File | What it covers |
|------|----------------|
| `consept.md` | Продукт, проблема, MVP, метрики, риски, roadmap |
| `bot.md` | Роль бота, сценарии, core-функции, UX 2–3 клика |
| `chennel.md` | Позиционирование канала, форматы постов, связка с ботом |

## Project Map (progressive disclosure)

| Area | File | What it covers |
|------|------|----------------|
| Whole repo | `STRUCTURE.md` | Текущая структура каталогов и файлов; обновлять при изменениях |
| Secrets / config | `.env.example` | Шаблон переменных окружения (скопировать в `.env`, не коммитить `.env`) |

Когда появится код (например `bot/`, `api/`), добавь в `STRUCTURE.md` отдельные подсекции и при необходимости локальные `STRUCTURE.md` внутри пакетов — по аналогии с крупными монорепами.

## Tech Stack

Зафиксировано для MVP:

| Слой | Выбор | Заметки |
|------|--------|---------|
| Рантайм | **Python 3.12+** | |
| Telegram | **aiogram 3** | меню, FSM, callback-инлайны под сценарии из `bot.md` |
| БД | **PostgreSQL** | прод и локальная разработка; при необходимости Docker для инстанса |
| Доступ к БД | **SQLAlchemy 2.x (async)** + **asyncpg** | типичная связка с aiogram; альтернативы обсуждаем отдельно |
| Миграции схемы | **Alembic** | ревизии рядом с кодом (каталог `alembic/` после `alembic init`) |

Деплой (Docker, PaaS, systemd) — появится отдельной строкой в этом разделе, когда выберешь способ.

Локальная БД: **`docker compose up -d`** в корне (см. `docker-compose.yml`). Скопируй **`.env.example` → `.env`**, подставь `BOT_TOKEN` и `DATABASE_URL` (для compose — строка из комментария в `.env.example`).

## Essential Commands

Из корня репозитория (после `python -m venv .venv && source .venv/bin/activate` и `pip install -e .`):

```bash
docker compose up -d
alembic upgrade head
python -m bot
```

Новая миграция после изменения моделей:

```bash
alembic revision --autogenerate -m "short description"
alembic upgrade head
```

## Rules (always apply)

- **Обновляй `STRUCTURE.md`** после создания/удаления значимых файлов или смены архитектуры.
- **Импорты в начале файла**, не внутри функций; при правках выноси импорты наверх.
- **Не плодить отдельные “отчётные” .md** о каждой правке — фиксируй состояние в `STRUCTURE.md` и при необходимости в `README.md`.
- **MVP-фокус** из `consept.md` / `bot.md`: не тащить в первую версию рейтинги, сложные рекомендации и монетизацию, если это явно вынесено в «не делаем».

## Commit Guidelines

- Без строк вроде «Generated with Claude» и без `Co-Authored-By`.
- Сообщение отражает только то, что вошло в коммит; тема — коротко, тело — по необходимости.
- Формат коммитов: см. `.cursor/commands/commit.md` (Conventional Commits; опциональный префикс задачи из имени ветки).

## Cursor / Claude Skills

В `.claude/skills/` лежат переносимые навыки из рабочего референса:

- `composition-patterns` — композиция React-компонентов (если появится веб-админка или мини-приложение).
- `web-design-guidelines` — аудит UI по Web Interface Guidelines (через загрузку актуального `command.md` из репозитория Vercel).

Подключай skill, когда задача явно про эту область.

## Optional: Task ID in Commits

Если заведёшь трекер (Jira, Linear) и префиксы в ветках вроде `TD-123-feature`, синхронизируй правило в `.cursor/commands/commit.md` с вашим форматом ключа.
