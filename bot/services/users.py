from aiogram.types import User as TgUser
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import User


def is_profile_complete(user: User) -> bool:
    if not user.avatar_file_id or not user.avatar_file_id.strip():
        return False
    if user.age is None or user.age < 14 or user.age > 99:
        return False
    if not user.bio or len(user.bio.strip()) < 10:
        return False
    return True


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


async def update_user_profile(
    session: AsyncSession,
    *,
    user_id: int,
    avatar_file_id: str,
    age: int,
    bio: str,
) -> None:
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            avatar_file_id=avatar_file_id,
            age=age,
            bio=bio,
            updated_at=func.now(),
        ),
    )


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
