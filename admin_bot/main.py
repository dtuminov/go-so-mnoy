import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from admin_bot.config import get_admin_settings
from admin_bot.handlers import router as handlers_router
from admin_bot.scheduler import create_admin_scheduler
from bot.db import session as db_session
from bot.middlewares import DbSessionMiddleware

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_admin_settings()
    db_session.init_db(settings.database_url)

    bot = Bot(
        settings.admin_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.include_router(handlers_router)

    scheduler = create_admin_scheduler(bot, db_session.get_sessionmaker())

    @dp.startup.register
    async def _on_startup() -> None:
        scheduler.start()
        logger.info("Admin bot starting (polling)")

    @dp.shutdown.register
    async def _on_shutdown() -> None:
        scheduler.shutdown(wait=False)
        await db_session.dispose_db()
        logger.info("Admin bot stopped")

    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())
