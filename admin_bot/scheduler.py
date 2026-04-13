"""Scheduler админ-бота: уведомление админов о новых заявках на модерацию."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from admin_bot.config import get_admin_settings
from admin_bot.handlers.moderation import _decision_keyboard
from bot.constants import ACTIVITY_PENDING_REVIEW
from bot.models import Activity, User
from bot.utils.formatting import esc, format_datetime_msk

logger = logging.getLogger(__name__)


async def _notify_new_pending(bot: Bot, factory: async_sessionmaker) -> None:
    settings = get_admin_settings()

    async with factory() as session:
        stmt = (
            select(Activity)
            .where(Activity.status == ACTIVITY_PENDING_REVIEW)
            .where(Activity.moderation_notified.is_(False))
            .order_by(Activity.created_at.asc())
        )
        activities = list((await session.execute(stmt)).scalars().all())

        for activity in activities:
            creator = await session.get(User, activity.creator_id)
            creator_name = "?"
            if creator:
                creator_name = creator.first_name or creator.username or f"uid:{creator.id}"

            kind_label = "Событие" if activity.is_event else "Ищу компанию"
            lines = [
                f"🆕 <b>Новая заявка на модерацию</b>\n",
                f"<b>{esc(activity.title)}</b>",
                f"Тип: {kind_label} | ID: {activity.id}",
                f"Автор: {esc(creator_name)}",
            ]
            if activity.starts_at:
                lines.append(f"Начало: {format_datetime_msk(activity.starts_at)}")
            if activity.place_text:
                from urllib.parse import quote
                maps_url = f"https://yandex.ru/maps/?text={quote(activity.place_text)}"
                lines.append(f'Место: <a href="{maps_url}">{esc(activity.place_text)}</a>')
            lines.append(f"\n/pending — открыть очередь модерации")
            text = "\n".join(lines)

            kb = _decision_keyboard(activity.id)
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(
                        admin_id, text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb.as_markup(),
                    )
                except Exception as e:
                    logger.warning("Cannot notify admin %s: %s", admin_id, e)

            await session.execute(
                update(Activity)
                .where(Activity.id == activity.id)
                .values(moderation_notified=True)
            )

        await session.commit()


def create_admin_scheduler(
    bot: Bot, factory: async_sessionmaker,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        _notify_new_pending,
        trigger="interval",
        seconds=30,
        args=[bot, factory],
        id="notify_new_pending",
        replace_existing=True,
    )
    return scheduler
