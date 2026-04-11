"""Чтение и запись пользовательских фильтров поиска.

Структура `users.search_prefs`:
    {
        "event_tag_ids":   [int, ...],  # фильтр ленты событий
        "seeking_tag_ids": [int, ...],  # фильтр ленты «ищу компанию»
    }

Отсутствие ключа или пустой список — «фильтр не задан, показываем всё».
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import User

EVENT_KEY = "event_tag_ids"
SEEKING_KEY = "seeking_tag_ids"


def _prefs(user: User) -> dict:
    return dict(user.search_prefs or {})


def get_event_tag_filter(user: User) -> list[int]:
    raw = _prefs(user).get(EVENT_KEY) or []
    return [int(x) for x in raw if isinstance(x, int) or str(x).isdigit()]


def get_seeking_tag_filter(user: User) -> list[int]:
    raw = _prefs(user).get(SEEKING_KEY) or []
    return [int(x) for x in raw if isinstance(x, int) or str(x).isdigit()]


async def _set_filter(
    session: AsyncSession,
    *,
    user: User,
    key: str,
    tag_ids: list[int],
) -> None:
    prefs = _prefs(user)
    # нормализуем: уникальные id, отсортированные по возрастанию
    clean = sorted({int(t) for t in tag_ids})
    if clean:
        prefs[key] = clean
    else:
        prefs.pop(key, None)
    # Пустой dict сохраняем как None — чище в БД.
    new_value = prefs or None
    await session.execute(
        update(User).where(User.id == user.id).values(search_prefs=new_value),
    )
    user.search_prefs = new_value


async def set_event_tag_filter(
    session: AsyncSession,
    *,
    user: User,
    tag_ids: list[int],
) -> None:
    await _set_filter(session, user=user, key=EVENT_KEY, tag_ids=tag_ids)


async def set_seeking_tag_filter(
    session: AsyncSession,
    *,
    user: User,
    tag_ids: list[int],
) -> None:
    await _set_filter(session, user=user, key=SEEKING_KEY, tag_ids=tag_ids)


async def clear_event_tag_filter(session: AsyncSession, *, user: User) -> None:
    await set_event_tag_filter(session, user=user, tag_ids=[])


async def clear_seeking_tag_filter(session: AsyncSession, *, user: User) -> None:
    await set_seeking_tag_filter(session, user=user, tag_ids=[])
