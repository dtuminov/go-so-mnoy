from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.constants import MOSCOW_CITY_ID, SEEKING_PUBLISHED
from bot.models import (
    CompanySeeking,
    CompanySeekingResponse,
    Tag,
    User,
    seeking_tags,
)


async def list_published_seekings(
    session: AsyncSession,
    *,
    city_id: int = MOSCOW_CITY_ID,
    tag_ids: list[int] | None = None,
    limit: int = 100,
) -> list[CompanySeeking]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(CompanySeeking)
        .where(CompanySeeking.city_id == city_id)
        .where(CompanySeeking.status == SEEKING_PUBLISHED)
        .where(CompanySeeking.expires_at >= now)
        .options(selectinload(CompanySeeking.tags))
        .order_by(CompanySeeking.created_at.desc())
        .limit(limit)
    )
    if tag_ids:
        subq = (
            select(seeking_tags.c.seeking_id)
            .where(seeking_tags.c.seeking_id == CompanySeeking.id)
            .where(seeking_tags.c.tag_id.in_(tag_ids))
        )
        stmt = stmt.where(subq.exists())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_seeking(session: AsyncSession, seeking_id: int) -> CompanySeeking | None:
    stmt = (
        select(CompanySeeking)
        .where(CompanySeeking.id == seeking_id)
        .options(selectinload(CompanySeeking.tags))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_responses(session: AsyncSession, seeking_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(CompanySeekingResponse)
        .where(CompanySeekingResponse.seeking_id == seeking_id)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def get_author(session: AsyncSession, seeking: CompanySeeking) -> User | None:
    result = await session.execute(select(User).where(User.id == seeking.author_id))
    return result.scalar_one_or_none()


async def user_responded(
    session: AsyncSession,
    *,
    seeking_id: int,
    user_id: int,
) -> bool:
    """Добавляет отклик. Возвращает True если добавлено, False если уже был."""
    existing = await session.execute(
        select(CompanySeekingResponse.id).where(
            CompanySeekingResponse.seeking_id == seeking_id,
            CompanySeekingResponse.user_id == user_id,
        )
    )
    if existing.first() is not None:
        return False
    session.add(CompanySeekingResponse(seeking_id=seeking_id, user_id=user_id))
    return True


async def close_seeking(
    session: AsyncSession,
    *,
    seeking_id: int,
    author_id: int,
) -> bool:
    """Закрывает заявку. Только автор может закрыть. Возвращает True при успехе."""
    result = await session.execute(
        select(CompanySeeking.id).where(
            CompanySeeking.id == seeking_id,
            CompanySeeking.author_id == author_id,
        )
    )
    if result.first() is None:
        return False
    await session.execute(
        update(CompanySeeking)
        .where(CompanySeeking.id == seeking_id)
        .values(status="closed")
    )
    return True


async def get_user_seekings(
    session: AsyncSession,
    *,
    author_id: int,
    limit: int = 10,
) -> list[CompanySeeking]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(CompanySeeking)
        .where(CompanySeeking.author_id == author_id)
        .where(CompanySeeking.expires_at >= now)
        .where(CompanySeeking.status.in_(["pending_review", "published"]))
        .order_by(CompanySeeking.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_seeking_responders(
    session: AsyncSession,
    *,
    seeking_id: int,
) -> list[tuple[CompanySeekingResponse, User]]:
    stmt = (
        select(CompanySeekingResponse, User)
        .join(User, User.id == CompanySeekingResponse.user_id)
        .where(CompanySeekingResponse.seeking_id == seeking_id)
        .order_by(CompanySeekingResponse.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.all())


async def create_seeking_draft(
    session: AsyncSession,
    *,
    author_id: int,
    city_id: int,
    title: str,
    body: str,
    expires_at: datetime,
    tag_ids: list[int] | None = None,
) -> CompanySeeking:
    seeking = CompanySeeking(
        city_id=city_id,
        author_id=author_id,
        title=title,
        body=body,
        expires_at=expires_at,
        status="pending_review",
    )
    session.add(seeking)
    await session.flush()
    if tag_ids:
        tags = (
            await session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        ).scalars().all()
        seeking.tags = list(tags)
        await session.flush()
    return seeking
