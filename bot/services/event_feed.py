from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MOSCOW_CITY_ID
from bot.keyboards.events_feed import events_feed_keyboard, format_event_feed_text
from bot.models import Tag
from bot.services.events import (
    count_participants,
    is_user_joined_event,
    list_published_events,
)
from bot.services.tags import get_tags_by_ids


async def build_event_feed_view(
    session: AsyncSession,
    *,
    index: int,
    city_id: int = MOSCOW_CITY_ID,
    tag_ids: list[int] | None = None,
    viewer_user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup] | None:
    events = await list_published_events(session, city_id=city_id, tag_ids=tag_ids)
    if not events:
        return None
    idx = max(0, min(index, len(events) - 1))
    ev = events[idx]
    n = await count_participants(session, ev.id)
    active_filter: list[Tag] = (
        await get_tags_by_ids(session, tag_ids) if tag_ids else []
    )
    joined = False
    if viewer_user_id is not None:
        joined = await is_user_joined_event(
            session, event_id=ev.id, user_id=viewer_user_id,
        )
    text = format_event_feed_text(ev, participants=n, active_filter=active_filter)
    kb = events_feed_keyboard(
        idx,
        len(events),
        ev.id,
        chat_url=ev.chat_url,
        viewer_joined=joined,
    )
    return text, kb
