"""Background scheduler: уведомления о публикации + напоминания за 2 часа до события.

После унификации работает поверх единой `Activity`:
- publish-нотификация — для kind='event' и kind='seeking';
- 2-часовое напоминание — только для событий (у них есть `starts_at`).
"""

from __future__ import annotations

import logging
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.constants import (
    ACTIVITY_EVENT,
    ACTIVITY_PUBLISHED,
    ACTIVITY_REJECTED,
    ACTIVITY_SEEKING,
    MEMBER_JOINED,
)
from bot.models import Activity, ActivityMember, User
from bot.utils.formatting import esc, format_datetime_msk

logger = logging.getLogger(__name__)


# ── уведомление о публикации ────────────────────────────────────────────────


async def _notify_published(bot: Bot, factory: async_sessionmaker) -> None:
    async with factory() as session:
        stmt = (
            select(Activity)
            .where(Activity.status == ACTIVITY_PUBLISHED)
            .where(Activity.published_notified.is_(False))
        )
        activities = list((await session.execute(stmt)).scalars().all())

        for activity in activities:
            creator = await session.get(User, activity.creator_id)
            if creator:
                if activity.kind == ACTIVITY_EVENT:
                    text = (
                        f"✅ Твоё событие опубликовано!\n\n"
                        f"<b>{esc(activity.title)}</b>\n"
                        f"{format_datetime_msk(activity.starts_at)}\n"
                        f'📍 <a href="https://yandex.ru/maps/?text={quote(activity.place_text)}">{esc(activity.place_text)}</a>\n\n'
                        f"Оно появилось в ленте — люди уже могут записываться."
                    )
                else:
                    text = (
                        f"✅ Твоя заявка опубликована!\n\n"
                        f"<b>{esc(activity.title)}</b>\n\n"
                        f"Она появилась в разделе «🤝 Найти компанию» — "
                        f"люди могут откликнуться."
                    )
                try:
                    await bot.send_message(
                        creator.telegram_id,
                        text,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    logger.warning(
                        "Cannot notify creator %s: %s", creator.telegram_id, e,
                    )

            await session.execute(
                update(Activity)
                .where(Activity.id == activity.id)
                .values(published_notified=True)
            )

        await session.commit()


# ── уведомление об отклонении ──────────────────────────────────────────────


async def _notify_rejected(bot: Bot, factory: async_sessionmaker) -> None:
    async with factory() as session:
        stmt = (
            select(Activity)
            .where(Activity.status == ACTIVITY_REJECTED)
            .where(Activity.published_notified.is_(False))
        )
        activities = list((await session.execute(stmt)).scalars().all())

        for activity in activities:
            creator = await session.get(User, activity.creator_id)
            if creator:
                if activity.kind == ACTIVITY_EVENT:
                    text = (
                        f"❌ Твоё событие не прошло модерацию.\n\n"
                        f"<b>{esc(activity.title)}</b>\n\n"
                        f"Попробуй создать новое с более подробным описанием."
                    )
                else:
                    text = (
                        f"❌ Твоя заявка не прошла модерацию.\n\n"
                        f"<b>{esc(activity.title)}</b>\n\n"
                        f"Попробуй создать новую с более подробным описанием."
                    )
                try:
                    await bot.send_message(
                        creator.telegram_id,
                        text,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    logger.warning(
                        "Cannot notify creator %s: %s", creator.telegram_id, e,
                    )

            await session.execute(
                update(Activity)
                .where(Activity.id == activity.id)
                .values(published_notified=True)
            )

        await session.commit()


# ── напоминание участникам за 2 часа до события ─────────────────────────────


async def _send_reminders(bot: Bot, factory: async_sessionmaker) -> None:
    async with factory() as session:
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(hours=1, minutes=50)
        window_end = now + timedelta(hours=2, minutes=10)

        stmt = (
            select(Activity)
            .where(Activity.kind == ACTIVITY_EVENT)
            .where(Activity.status == ACTIVITY_PUBLISHED)
            .where(Activity.reminder_sent.is_(False))
            .where(Activity.starts_at >= window_start)
            .where(Activity.starts_at <= window_end)
        )
        events = list((await session.execute(stmt)).scalars().all())

        for event in events:
            members_stmt = (
                select(ActivityMember)
                .where(ActivityMember.activity_id == event.id)
                .where(ActivityMember.status == MEMBER_JOINED)
            )
            members = list((await session.execute(members_stmt)).scalars().all())

            for member in members:
                user = await session.get(User, member.user_id)
                if not user:
                    continue
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"⏰ <b>Через ~2 часа</b> начинается событие, на которое ты записан!\n\n"
                        f"<b>{esc(event.title)}</b>\n"
                        f"{format_datetime_msk(event.starts_at)}\n"
                        f'📍 <a href="https://yandex.ru/maps/?text={quote(event.place_text)}">{esc(event.place_text)}</a>',
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    logger.warning("Cannot send reminder to %s: %s", user.telegram_id, e)

            await session.execute(
                update(Activity)
                .where(Activity.id == event.id)
                .values(reminder_sent=True)
            )

        await session.commit()


# ── публичный интерфейс ─────────────────────────────────────────────────────


def create_scheduler(bot: Bot, factory: async_sessionmaker) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        _notify_published,
        trigger="interval",
        minutes=2,
        args=[bot, factory],
        id="notify_published",
        replace_existing=True,
    )
    scheduler.add_job(
        _notify_rejected,
        trigger="interval",
        minutes=2,
        args=[bot, factory],
        id="notify_rejected",
        replace_existing=True,
    )
    scheduler.add_job(
        _send_reminders,
        trigger="interval",
        minutes=5,
        args=[bot, factory],
        id="send_reminders",
        replace_existing=True,
    )

    return scheduler
