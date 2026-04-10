import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_settings
from bot.db import session as db_session
from bot.handlers import router as handlers_router
from bot.middlewares import DbSessionMiddleware

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    db_session.init_db(settings.database_url)

    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.include_router(handlers_router)

    @dp.startup.register
    async def _on_startup() -> None:
        logger.info("Bot starting (polling)")

    @dp.shutdown.register
    async def _on_shutdown() -> None:
        await db_session.dispose_db()
        logger.info("Bot stopped")

    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())
