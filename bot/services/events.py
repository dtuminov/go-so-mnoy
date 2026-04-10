from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import (
    EVENT_PENDING_REVIEW,
    EVENT_PUBLISHED,
    MOSCOW_CITY_ID,
    PARTICIPANT_JOINED,
)
from bot.models import Event, EventParticipant, User


async def list_published_events(
    session: AsyncSession,
    *,
    city_id: int = MOSCOW_CITY_ID,
    limit: int = 15,
) -> list[Event]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(Event)
        .where(Event.city_id == city_id)
        .where(Event.status == EVENT_PUBLISHED)
        .where(Event.starts_at >= now)
        .order_by(Event.starts_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_event(session: AsyncSession, event_id: int) -> Event | None:
    result = await session.execute(select(Event).where(Event.id == event_id))
    return result.scalar_one_or_none()


async def count_participants(session: AsyncSession, event_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(EventParticipant)
        .where(EventParticipant.event_id == event_id)
        .where(EventParticipant.status == PARTICIPANT_JOINED)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def user_joined_event(
    session: AsyncSession,
    *,
    event_id: int,
    user_id: int,
) -> bool:
    existing = await session.execute(
        select(EventParticipant.id).where(
            EventParticipant.event_id == event_id,
            EventParticipant.user_id == user_id,
        ),
    )
    if existing.first() is not None:
        return False
    session.add(
        EventParticipant(
            event_id=event_id,
            user_id=user_id,
            status=PARTICIPANT_JOINED,
        ),
    )
    return True


async def create_event_draft(
    session: AsyncSession,
    *,
    organizer_id: int,
    city_id: int,
    title: str,
    description: str,
    starts_at: datetime,
    place_text: str,
) -> Event:
    event = Event(
        city_id=city_id,
        organizer_id=organizer_id,
        title=title,
        description=description,
        starts_at=starts_at,
        place_text=place_text,
        status=EVENT_PENDING_REVIEW,
    )
    session.add(event)
    await session.flush()
    return event


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()
