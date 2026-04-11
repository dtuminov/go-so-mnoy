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
| `scripts/approve_all.sh` | Публикует все `pending_review` события и заявки (опции `--events-only`, `--seekings-only`) |

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
| `bot/models/` | `User` (+ `search_prefs` JSONB), `City`, `Event` (+ `chat_url`), `EventParticipant` (+ `chat_invite_notified`), `CompanySeeking` (+ `chat_url`), `CompanySeekingResponse` (+ `chat_invite_notified`), `Tag`, ассоциативные `event_tags` / `seeking_tags` (в `associations.py`) |
| `bot/services/users.py` | upsert, profile check, update profile |
| `bot/services/events.py` | события: CRUD, участники, leave, cancel, joined/organized lists, фильтр по тегам в `list_published_events`, `update_event_chat_url`, `is_user_joined_event` |
| `bot/services/event_feed.py` | карточка ленты событий с пагинацией, активным тег-фильтром и кнопкой «💬 Чат» для записавшихся |
| `bot/services/company_seeking.py` | заявки: CRUD, отклики, close, responders list, фильтр по тегам в `list_published_seekings`, `update_seeking_chat_url`, `is_user_responded_seeking` |
| `bot/services/tags.py` | чтение активных тегов, выборка по id |
| `bot/services/search_prefs.py` | get/set фильтров пользователя в `users.search_prefs` |
| `bot/services/notifications.py` | `notify_actor_about_new_member` — DM организатору/автору при join/отклике (общий для events и seekings) |
| `bot/services/chat_invite_notify.py` | Рассылка инвайт-ссылки участникам/откликнувшимся с флагом `chat_invite_notified`, mark-helpers |
| `bot/keyboards/main_menu.py` | Reply-меню: найти событие, найти компанию, создать событие, 👤 Мой профиль |
| `bot/keyboards/events_feed.py` | Инлайн-пагинация ленты событий, `format_event_card_text`, `format_event_feed_text`, кнопки «🔎 Фильтры» и «💬 Чат события» для записавшихся |
| `bot/keyboards/tag_picker.py` | Универсальный мульти-селект тегов с параметризованным callback-префиксом |
| `bot/handlers/common.py` | `/start`, `/help`, deep link `event_` / `seek_` |
| `bot/handlers/menu.py` | Обработка кнопок главного меню; профиль: записи, организованные события (с 💬 Чат), заявки (с 💬 Чат) |
| `bot/handlers/events.py` | Лента событий (`evp:`), карточка (`e:`), запись (`j:`) с DM-приглашением в чат и симметричным уведомлением организатора, отписка (`uleave:`), участники (`ep:`), отмена (`ecancel:`) |
| `bot/handlers/create_event.py` | FSM создания события (6 шагов: title → description → starts_at → place → chat_url → tags); шаг `chat_url` можно пропустить |
| `bot/handlers/profile.py` | FSM анкеты (фото → возраст → bio); `profile:edit`; авто-запись после анкеты |
| `bot/handlers/event_chat.py` | Управление ссылкой на чат из профиля: `evch:*` для событий, `skch:*` для заявок; FSM `EditChatSG`; рассылка при первом заполнении |
| `bot/handlers/company_seeking.py` | Лента заявок (`sk:`), отклик (`sr:`) c DM-приглашением и вызовом общего `notify_actor_about_new_member`, отклики автора (`skp:`), закрыть (`sk:close:`), FSM создания заявки (5 шагов: title → body → duration → chat_url → tags) |
| `bot/handlers/filters.py` | Пикер тег-фильтров для лент: `tp:e:*` (события) и `tp:s:*` (заявки) — open/toggle/apply/clear/cancel |
| `bot/utils/` | Форматирование дат (МСК), парсер даты для FSM, `chat_link.py` — валидатор/нормализатор Telegram-ссылок |
| `alembic/versions/001_initial_users.py` | Таблица `users` |
| `alembic/versions/002_domain_core.py` | `cities`, `events`, `event_participants`, `company_seekings`, `company_seeking_responses`; поля профиля в `users` |
| `alembic/versions/003_user_profile.py` | `avatar_file_id`, `age`, `bio` в `users` |
| `alembic/versions/004_notification_flags.py` | `published_notified` на events/seekings, `reminder_sent` на events |
| `alembic/versions/005_tags_and_search_prefs.py` | `tags`, `event_tags`, `seeking_tags`, `users.search_prefs` (JSONB); сидится стартовый набор тегов |
| `alembic/versions/006_chat_links_and_notify_flags.py` | `events.chat_url`, `company_seekings.chat_url`, `event_participants.chat_invite_notified`, `company_seeking_responses.chat_invite_notified` |
