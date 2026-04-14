from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import City


async def list_all_cities(session: AsyncSession) -> list[City]:
    result = await session.execute(select(City).order_by(City.name))
    return list(result.scalars().all())


async def search_cities(session: AsyncSession, query: str, limit: int = 5) -> list[City]:
    pattern = f"%{query}%"
    result = await session.execute(
        select(City)
        .where(City.name.ilike(pattern))
        .order_by(City.name)
        .limit(limit),
    )
    return list(result.scalars().all())
