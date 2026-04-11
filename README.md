# go-so-mnoy

Telegram-бот и связанный канал как MVP: «куда пойти сегодня и с кем». Продуктовые требования — в `consept.md`, `bot.md`, `chennel.md`.

## Разработка

Карта репозитория и первый запуск: **`STRUCTURE.md`**. Контекст для AI и стек: **`CLAUDE.md`**.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
# В .env задай BOT_TOKEN и DATABASE_URL (пример в .env.example). Иначе alembic и бот не стартуют.
docker compose up -d
alembic upgrade head
python -m bot
```

Если **`docker compose`** не поднимается из‑за занятого порта **5432**, останови другой Postgres на этом порту или измени в `docker-compose.yml` проброс (например `5433:5432`) и укажи тот порт в `DATABASE_URL`.

## Модерация событий (пока без админки в боте)

Новые события сохраняются со статусом `pending_review` и **не попадают** в ленту, пока статус не станет `published`. Для теста можно выставить вручную в PostgreSQL.

Подключение к БД из контейнера `docker compose` (имя контейнера может быть `go-so-mnoy-postgres-1`):

```bash
docker exec -it go-so-mnoy-postgres-1 psql -U go_so_mnoy -d go_so_mnoy
```

Дальше в `psql`:

```sql
-- посмотреть события и статусы
SELECT id, title, status, starts_at FROM events ORDER BY id DESC LIMIT 10;

-- опубликовать конкретное (подставь свой id)
UPDATE events SET status = 'published' WHERE id = 1;

-- выйти
\q
```

Если Postgres не в Docker — выполни те же запросы в своём клиенте к базе из `DATABASE_URL`. После `UPDATE` бота перезапускать не обязательно.
