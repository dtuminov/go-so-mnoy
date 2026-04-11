from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.session import get_sessionmaker


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        factory = get_sessionmaker()
        async with factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except SQLAlchemyError:
                # Ошибка самой БД — откатываем.
                await session.rollback()
                raise
            except Exception:
                # Ошибка Telegram API или любая другая не-БД ошибка —
                # DB-изменения уже сделаны корректно, коммитим их.
                try:
                    await session.commit()
                except SQLAlchemyError:
                    await session.rollback()
                raise
