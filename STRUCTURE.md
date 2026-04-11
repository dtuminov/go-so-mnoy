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
| `bot/models/` | `User` (+ `search_prefs` JSONB), `City`, `Activity` (kind/visibility/chat_url/expires_at), `ActivityMember` (status pending/joined + `chat_invite_notified`), `Tag`, ассоциативная `activity_tags` (в `associations.py`) |
| `bot/services/users.py` | upsert, profile check, update profile |
| `bot/services/activities.py` | CRUD единой `Activity`: CRUD, members, join/leave, approve/reject, cancel/close, фильтр по тегам в `list_published_activities`, `update_chat_url`, `update_visibility`, `is_user_joined`, helpers профиля |
| `bot/services/activity_feed.py` | Сборка карточки ленты `Activity` (text+keyboard) для events и seekings — единая функция с параметром `kind` |
| `bot/services/tags.py` | чтение активных тегов, выборка по id |
| `bot/services/search_prefs.py` | get/set фильтров пользователя в `users.search_prefs` (отдельно для event-tag и seeking-tag) |
| `bot/services/notifications.py` | DM-уведомления: `notify_creator_about_new_member` (с веткой `is_pending` и кнопками ✅/❌), `notify_user_about_decision` (approve/reject), `notify_members_about_cancel` |
| `bot/services/chat_invite_notify.py` | Рассылка инвайт-ссылки joined-членам активности с флагом `chat_invite_notified`, `mark_member_notified` |
| `bot/services/profile_view.py` | `build_profile_view` + `rerender_profile_card` — карточка профиля и in-place перерисовка после мутаций |
| `bot/keyboards/main_menu.py` | Reply-меню: найти событие, найти компанию, создать событие, ищу компанию, 👤 Мой профиль, ❌ Отменить |
| `bot/keyboards/activity_feed.py` | `format_activity_card_text`, `format_activity_feed_text`, `activity_feed_keyboard` — единая клавиатура с поддержкой viewer_joined / viewer_pending / chat_url |
| `bot/keyboards/tag_picker.py` | Универсальный мульти-селект тегов с параметризованным callback-префиксом |
| `bot/handlers/common.py` | `/start`, `/help`, канонический deep link `act_<id>` (старые `event_`/`seek_` → «устарело») |
| `bot/handlers/menu.py` | Кнопки главного меню; «📍 Найти событие» / «🤝 Найти компанию» — единая лента `Activity` с разным `kind`; открытие профиля |
| `bot/handlers/activity.py` | Действия над `Activity`: пагинация ленты (`af:g/c:`), join (`aj:`) с веткой open/private, leave (`al:`), members/responders (`amem:`), approve/reject (`amap:` / `amrj:`), cancel (`acan:`), close (`aclose:`) |
| `bot/handlers/activity_create.py` | FSM создания: `CreateEventSG` (6 шагов) и `CreateSeekingSG` (5 шагов) с шагом chat_url и опцией пропуска |
| `bot/handlers/activity_chat.py` | Управление настройками активности из профиля: chat_url (`actch:*`, `EditChatSG`, broadcast при первом заполнении) и visibility (`avis:show/set:*`) |
| `bot/handlers/profile.py` | FSM анкеты (фото → возраст → bio); `profile:edit`; авто-вступление в `pending_join_activity_id` после анкеты |
| `bot/handlers/filters.py` | Пикер тег-фильтров: `tp:e:*` (events lente) и `tp:s:*` (seekings lente) — open/toggle/apply/clear/cancel; пишет в `users.search_prefs` |
| `bot/utils/` | Форматирование дат (МСК), парсер даты для FSM, `chat_link.py` — валидатор/нормализатор Telegram-ссылок |
| `alembic/versions/001_initial_users.py` | Таблица `users` |
| `alembic/versions/002_domain_core.py` | `cities`, `events`, `event_participants`, `company_seekings`, `company_seeking_responses`; поля профиля в `users` |
| `alembic/versions/003_user_profile.py` | `avatar_file_id`, `age`, `bio` в `users` |
| `alembic/versions/004_notification_flags.py` | `published_notified` на events/seekings, `reminder_sent` на events |
| `alembic/versions/005_tags_and_search_prefs.py` | `tags`, `event_tags`, `seeking_tags`, `users.search_prefs` (JSONB); сидится стартовый набор тегов |
| `alembic/versions/006_chat_links_and_notify_flags.py` | `events.chat_url`, `company_seekings.chat_url`, `event_participants.chat_invite_notified`, `company_seeking_responses.chat_invite_notified` |
| `alembic/versions/007_unify_activities.py` | Слияние events+seekings в `activities`, event_participants+company_seeking_responses в `activity_members`, event_tags+seeking_tags в `activity_tags`. Копирование данных, дроп legacy-таблиц. Добавляет `visibility`. Для событий `expires_at = starts_at + 2h`. |
