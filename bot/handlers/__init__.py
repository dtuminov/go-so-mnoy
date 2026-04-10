from aiogram import Router

from bot.handlers import common, create_event, events, menu

router = Router()
router.include_router(create_event.router)
router.include_router(events.router)
router.include_router(menu.router)
router.include_router(common.router)
