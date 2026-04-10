from aiogram.types import User as TgUser
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import User


async def upsert_telegram_user(session: AsyncSession, tg: TgUser) -> User:
    stmt = (
        insert(User)
        .values(
            telegram_id=tg.id,
            username=tg.username,
            first_name=tg.first_name,
            last_name=tg.last_name,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "username": tg.username,
                "first_name": tg.first_name,
                "last_name": tg.last_name,
                "updated_at": func.now(),
            },
        )
        .returning(User)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def upsert_user_from_message(session: AsyncSession, message) -> User:
    tg = message.from_user
    if tg is None:
        raise ValueError("from_user is required")
    return await upsert_telegram_user(session, tg)
