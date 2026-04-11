from aiogram import Router

from bot.handlers import (
    activity,
    activity_chat,
    activity_create,
    common,
    filters,
    menu,
    profile,
    profile_nav,
)

router = Router()
router.include_router(profile.router)
router.include_router(profile_nav.router)
router.include_router(activity_chat.router)
router.include_router(activity_create.router)
router.include_router(activity.router)
router.include_router(filters.router)
router.include_router(menu.router)
router.include_router(common.router)
