from aiogram import Router

from bot.handlers import (
    common,
    company_seeking,
    create_event,
    events,
    filters,
    menu,
    profile,
)

router = Router()
router.include_router(profile.router)
router.include_router(company_seeking.router)
router.include_router(create_event.router)
router.include_router(events.router)
router.include_router(filters.router)
router.include_router(menu.router)
router.include_router(common.router)
