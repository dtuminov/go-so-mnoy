from aiogram import Router

from admin_bot.handlers.moderation import router as moderation_router

router = Router(name="admin_root")
router.include_router(moderation_router)
