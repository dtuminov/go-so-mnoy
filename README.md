# go-so-mnoy

Telegram-бот и связанный канал как MVP: «куда пойти сегодня и с кем». Продуктовые требования — в `consept.md`, `bot.md`, `chennel.md`.

## Разработка

Карта репозитория и первый запуск: **`STRUCTURE.md`**. Контекст для AI и стек: **`CLAUDE.md`**.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
docker compose up -d
alembic upgrade head
python -m bot
```
