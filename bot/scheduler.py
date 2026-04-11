"""Background scheduler: уведомления о публикации + напоминания за 2 часа до события."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.constants import EVENT_PUBLISHED, PARTICIPANT_JOINED, SEEKING_PUBLISHED
from bot.models import CompanySeeking, Event, EventParticipant, User
from bot.utils.formatting import esc, format_datetime_msk

logger = logging.getLogger(__name__)


# ── уведомление о публикации события ─────────────────────────────────────────

async def _notify_published_events(bot: Bot, factory: async_sessionmaker) -> None:
    async with factory() as session:
        stmt = (
            select(Event)
            .where(Event.status == EVENT_PUBLISHED)
            .where(Event.published_notified.is_(False))
        )
        events = list((await session.execute(stmt)).scalars().all())

        for event in events:
            organizer = await session.get(User, event.organizer_id)
            if organizer:
                try:
                    await bot.send_message(
                        organizer.telegram_id,
                        f"✅ Твоё событие опубликовано!\n\n"
                        f"<b>{esc(event.title)}</b>\n"
                        f"{format_datetime_msk(event.starts_at)}\n"
                        f"📍 {esc(event.place_text)}\n\n"
                        f"Оно появилось в ленте — люди уже могут записываться.",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    logger.warning("Cannot notify organizer %s: %s", organizer.telegram_id, e)

            await session.execute(
                update(Event)
                .where(Event.id == event.id)
                .values(published_notified=True)
            )

        await session.commit()


# ── уведомление о публикации заявки «найти компанию» ─────────────────────────

async def _notify_published_seekings(bot: Bot, factory: async_sessionmaker) -> None:
    async with factory() as session:
        stmt = (
            select(CompanySeeking)
            .where(CompanySeeking.status == SEEKING_PUBLISHED)
            .where(CompanySeeking.published_notified.is_(False))
        )
        seekings = list((await session.execute(stmt)).scalars().all())

        for seeking in seekings:
            author = await session.get(User, seeking.author_id)
            if author:
                try:
                    await bot.send_message(
                        author.telegram_id,
                        f"✅ Твоя заявка опубликована!\n\n"
                        f"<b>{esc(seeking.title)}</b>\n\n"
                        f"Она появилась в разделе «🤝 Найти компанию» — люди могут откликнуться.",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    logger.warning("Cannot notify seeking author %s: %s", author.telegram_id, e)

            await session.execute(
                update(CompanySeeking)
                .where(CompanySeeking.id == seeking.id)
                .values(published_notified=True)
            )

        await session.commit()


# ── напоминание участникам за 2 часа до события ───────────────────────────────

async def _send_reminders(bot: Bot, factory: async_sessionmaker) -> None:
    async with factory() as session:
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(hours=1, minutes=50)
        window_end = now + timedelta(hours=2, minutes=10)

        stmt = (
            select(Event)
            .where(Event.status == EVENT_PUBLISHED)
            .where(Event.reminder_sent.is_(False))
            .where(Event.starts_at >= window_start)
            .where(Event.starts_at <= window_end)
        )
        events = list((await session.execute(stmt)).scalars().all())

        for event in events:
            participants_stmt = (
                select(EventParticipant)
                .where(EventParticipant.event_id == event.id)
                .where(EventParticipant.status == PARTICIPANT_JOINED)
            )
            participants = list((await session.execute(participants_stmt)).scalars().all())

            for participant in participants:
                user = await session.get(User, participant.user_id)
                if not user:
                    continue
                try:
                    await bot.send_message(
                        user.telegram_id,
                        f"⏰ <b>Через ~2 часа</b> начинается событие, на которое ты записан!\n\n"
                        f"<b>{esc(event.title)}</b>\n"
                        f"{format_datetime_msk(event.starts_at)}\n"
                        f"📍 {esc(event.place_text)}",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    logger.warning("Cannot send reminder to %s: %s", user.telegram_id, e)

            await session.execute(
                update(Event)
                .where(Event.id == event.id)
                .values(reminder_sent=True)
            )

        await session.commit()


# ── публичный интерфейс ───────────────────────────────────────────────────────

def create_scheduler(bot: Bot, factory: async_sessionmaker) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        _notify_published_events,
        trigger="interval",
        minutes=2,
        args=[bot, factory],
        id="notify_published_events",
        replace_existing=True,
    )
    scheduler.add_job(
        _notify_published_seekings,
        trigger="interval",
        minutes=2,
        args=[bot, factory],
        id="notify_published_seekings",
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
