from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MOSCOW_CITY_ID
from bot.keyboards.events_feed import events_feed_keyboard, format_event_feed_text
from bot.services.events import count_participants, list_published_events


async def build_event_feed_view(
    session: AsyncSession,
    *,
    index: int,
    city_id: int = MOSCOW_CITY_ID,
) -> tuple[str, InlineKeyboardMarkup] | None:
    events = await list_published_events(session, city_id=city_id)
    if not events:
        return None
    idx = max(0, min(index, len(events) - 1))
    ev = events[idx]
    n = await count_participants(session, ev.id)
    text = format_event_feed_text(ev, participants=n)
    kb = events_feed_keyboard(idx, len(events), ev.id)
    return text, kb
