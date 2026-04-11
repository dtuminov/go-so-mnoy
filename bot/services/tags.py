from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Tag


async def list_active_tags(session: AsyncSession) -> list[Tag]:
    stmt = (
        select(Tag)
        .where(Tag.is_active.is_(True))
        .order_by(Tag.sort_order.asc(), Tag.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_tags_by_ids(
    session: AsyncSession,
    tag_ids: list[int],
) -> list[Tag]:
    if not tag_ids:
        return []
    stmt = (
        select(Tag)
        .where(Tag.id.in_(tag_ids))
        .order_by(Tag.sort_order.asc(), Tag.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
