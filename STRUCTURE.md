# Структура репозитория

Актуальное описание каталогов и назначения файлов. **Обновляй этот файл** при добавлении или удалении значимых путей.

## Зафиксированный стек (MVP)

| Компонент | Технология |
|-----------|------------|
| Бот | Python **3.12+**, **aiogram 3**, FSM в **MemoryStorage** (для проды позже Redis) |
| БД | **PostgreSQL** |
| Миграции | **Alembic** (в связке с **SQLAlchemy 2 async** + **asyncpg**) |
| Фоновые задачи | **APScheduler 3** (уведомления о публикации + напоминания за 2 ч до события) |

Стек, локальная БД и команды — в **`CLAUDE.md`** (разделы **Tech Stack**, **Essential Commands**).

## Первый запуск

1. Python **3.12+**, виртуальное окружение и **`pip install -e .`** из корня репозитория.
2. Файл **`.env`** по образцу **`.env.example`**: обязательно непустые **`BOT_TOKEN`** и **`DATABASE_URL`** (`postgresql+asyncpg://…`). Опционально **`BOT_USERNAME`** (без `@`) для deep link из канала.
3. Поднять PostgreSQL: **`docker compose up -d`** (или свой инстанс).
4. **`alembic upgrade head`**
5. **`python -m bot`** (или **`./restart.sh`**)

## Корень

| Путь | Назначение |
|------|------------|
| `README.md` | Запуск, модерация через `psql` / SQL |
| `consept.md` | Продукт: видение, MVP, GTM, метрики |
| `bot.md` | Telegram-бот: сценарии и функции |
| `chennel.md` | Telegram-канал: контент и связка с ботом |
| `CLAUDE.md` | Контекст для AI: продукт, стек, команды, правила |
| `STRUCTURE.md` | Этот файл — карта репозитория |
| `.env.example` | Шаблон `.env` без секретов |
| `pyproject.toml` | Зависимости пакета (editable install) |
| `docker-compose.yml` | Локальный **PostgreSQL 16** |
| `alembic.ini` | Конфиг Alembic |
| `restart.sh` | Стоп старого процесса → `alembic upgrade head` → запуск бота |

## Код

| Путь | Назначение |
|------|------------|
| `bot/` | Пакет бота: `python -m bot` |
| `bot/__main__.py` | Точка входа CLI |
| `bot/main.py` | `Dispatcher`, middleware сессии БД, polling, запуск scheduler |
| `bot/config.py` | `pydantic-settings`: `BOT_TOKEN`, `DATABASE_URL`, `BOT_USERNAME` |
| `bot/constants.py` | ID Москвы, строковые статусы сущностей |
| `bot/scheduler.py` | APScheduler: уведомление о публикации (каждые 2 мин) + напоминание за 2 ч (каждые 5 мин) |
| `bot/db/` | `Base`, фабрика сессий |
| `bot/middlewares/` | `DbSessionMiddleware` — сессия и commit/rollback на апдейт |
| `bot/models/` | `User`, `City`, `Event`, `EventParticipant`, `CompanySeeking`, `CompanySeekingResponse` |
| `bot/services/users.py` | upsert, profile check, update profile |
| `bot/services/events.py` | события: CRUD, участники, leave, cancel, joined/organized lists |
| `bot/services/event_feed.py` | карточка ленты событий с пагинацией |
| `bot/services/company_seeking.py` | заявки: CRUD, отклики, close, responders list |
| `bot/keyboards/main_menu.py` | Reply-меню: найти событие, найти компанию, создать событие, 👤 Мой профиль |
| `bot/keyboards/events_feed.py` | Инлайн-пагинация ленты событий (⬅️ N/M ➡️) |
| `bot/handlers/common.py` | `/start`, `/help`, deep link `event_` / `seek_` |
| `bot/handlers/menu.py` | Обработка кнопок главного меню; профиль: записи + организованные события + заявки |
| `bot/handlers/events.py` | Лента событий (`evp:`), карточка (`e:`), запись (`j:`), отписка (`uleave:`), участники (`ep:`), отмена (`ecancel:`) |
| `bot/handlers/create_event.py` | FSM создания события (4 шага) |
| `bot/handlers/profile.py` | FSM анкеты (фото → возраст → bio); `profile:edit`; авто-запись после анкеты |
| `bot/handlers/company_seeking.py` | Лента заявок (`sk:`), отклик (`sr:`), отклики автора (`skp:`), закрыть (`sk:close:`), FSM создания заявки |
| `bot/utils/` | Форматирование дат (МСК), парсер даты для FSM |
| `alembic/versions/001_initial_users.py` | Таблица `users` |
| `alembic/versions/002_domain_core.py` | `cities`, `events`, `event_participants`, `company_seekings`, `company_seeking_responses`; поля профиля в `users` |
| `alembic/versions/003_user_profile.py` | `avatar_file_id`, `age`, `bio` в `users` |
| `alembic/versions/004_notification_flags.py` | `published_notified` на events/seekings, `reminder_sent` на events |
