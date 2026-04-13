"""Сборка карточки ленты `Activity` (текст + клавиатура).

Симметрично для kind='event' и kind='seeking' — одна функция.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import (
    ACTIVITY_EVENT,
    ACTIVITY_SEEKING,
    MEMBER_PENDING,
)
from bot.keyboards.activity_feed import (
    activity_feed_keyboard,
    format_activity_feed_text,
)
from bot.models import Tag
from bot.services.activities import (
    count_joined_members,
    get_creator_summary,
    get_user_membership,
    is_user_joined,
    list_published_activities,
)
from bot.services.tags import get_tags_by_ids


async def build_activity_feed_view(
    session: AsyncSession,
    *,
    kind: str,
    index: int,
    city_id: int,
    city_name: str = "",
    tag_ids: list[int] | None = None,
    viewer_user_id: int | None = None,
) -> tuple[str | None, str, InlineKeyboardMarkup] | None:
    """Возвращает `(cover_file_id, caption, keyboard)` или `None`, если
    лента пустая. `cover_file_id` — `str` для кастомной обложки или
    `None`, тогда caller через `bot.services.cover` подставит дефолт."""
    activities = await list_published_activities(
        session, kind=kind, city_id=city_id, tag_ids=tag_ids,
    )
    if not activities:
        return None
    idx = max(0, min(index, len(activities) - 1))
    act = activities[idx]
    members = await count_joined_members(session, act.id)
    active_filter: list[Tag] = (
        await get_tags_by_ids(session, tag_ids) if tag_ids else []
    )

    viewer_joined = False
    viewer_pending = False
    if viewer_user_id is not None:
        viewer_joined = await is_user_joined(
            session, activity_id=act.id, user_id=viewer_user_id,
        )
        if not viewer_joined:
            membership = await get_user_membership(
                session, activity_id=act.id, user_id=viewer_user_id,
            )
            viewer_pending = (
                membership is not None and membership.status == MEMBER_PENDING
            )

    author_name = author_age = None
    if act.kind == ACTIVITY_SEEKING:
        author_name, author_age = await get_creator_summary(session, act)

    text = format_activity_feed_text(
        act,
        members=members,
        active_filter=active_filter,
        author_name=author_name,
        author_age=author_age,
        city_name=city_name,
    )
    kb = activity_feed_keyboard(
        idx,
        len(activities),
        act.id,
        kind=kind,
        chat_url=act.chat_url,
        viewer_joined=viewer_joined,
        viewer_pending=viewer_pending,
    )
    return act.cover_file_id, text, kb
