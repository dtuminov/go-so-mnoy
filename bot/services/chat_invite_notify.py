"""Рассылка ссылки на чат участникам события / откликнувшимся на заявку.

Логика:
- При первом заполнении `chat_url` (переход NULL → value) вызывающий код
  вызывает `broadcast_event_chat_invite` или `broadcast_seeking_chat_invite`.
- Рассылаем только тем, у кого `chat_invite_notified=false`, и по успеху
  ставим флаг. Таким образом повторные правки ссылки или удаление/возврат
  не дают повторных уведомлений уже оповещённым.
- Ошибки доставки (юзер заблокировал бота и т.п.) глотаем — флаг всё
  равно ставим, чтобы не копить ретраи в будущем.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import PARTICIPANT_JOINED
from bot.models import (
    CompanySeeking,
    CompanySeekingResponse,
    Event,
    EventParticipant,
    User,
)
from bot.utils.formatting import esc


def _invite_keyboard(chat_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Открыть чат", url=chat_url)],
        ],
    )


async def _send_invite(
    bot: Bot,
    *,
    tg_id: int,
    text: str,
    chat_url: str,
) -> None:
    try:
        await bot.send_message(
            tg_id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=_invite_keyboard(chat_url),
            disable_web_page_preview=True,
        )
    except Exception:
        # Заблокировал бота / deactivated — пропускаем, флаг всё равно поставим.
        pass


async def broadcast_event_chat_invite(
    session: AsyncSession,
    bot: Bot,
    *,
    event: Event,
) -> int:
    """Шлёт всем записанным участникам приглашение в чат. Возвращает
    количество людей, кому отправили (флаг `chat_invite_notified=false`
    до начала рассылки)."""
    if not event.chat_url:
        return 0

    stmt = (
        select(EventParticipant, User)
        .join(User, User.id == EventParticipant.user_id)
        .where(EventParticipant.event_id == event.id)
        .where(EventParticipant.status == PARTICIPANT_JOINED)
        .where(EventParticipant.chat_invite_notified.is_(False))
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return 0

    text = (
        f"🎉 Организатор события «<b>{esc(event.title)}</b>» добавил чат.\n"
        "Заходи, чтобы обсудить детали!"
    )
    part_ids: list[int] = []
    for participant, user in rows:
        await _send_invite(bot, tg_id=user.telegram_id, text=text, chat_url=event.chat_url)
        part_ids.append(participant.id)

    await session.execute(
        update(EventParticipant)
        .where(EventParticipant.id.in_(part_ids))
        .values(chat_invite_notified=True),
    )
    return len(part_ids)


async def broadcast_seeking_chat_invite(
    session: AsyncSession,
    bot: Bot,
    *,
    seeking: CompanySeeking,
) -> int:
    if not seeking.chat_url:
        return 0

    stmt = (
        select(CompanySeekingResponse, User)
        .join(User, User.id == CompanySeekingResponse.user_id)
        .where(CompanySeekingResponse.seeking_id == seeking.id)
        .where(CompanySeekingResponse.chat_invite_notified.is_(False))
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return 0

    text = (
        f"🎉 Автор заявки «<b>{esc(seeking.title)}</b>» добавил чат.\n"
        "Заходи, чтобы обсудить детали!"
    )
    resp_ids: list[int] = []
    for response, user in rows:
        await _send_invite(bot, tg_id=user.telegram_id, text=text, chat_url=seeking.chat_url)
        resp_ids.append(response.id)

    await session.execute(
        update(CompanySeekingResponse)
        .where(CompanySeekingResponse.id.in_(resp_ids))
        .values(chat_invite_notified=True),
    )
    return len(resp_ids)


async def mark_participant_notified(
    session: AsyncSession,
    *,
    event_id: int,
    user_id: int,
) -> None:
    """Помечает запись участника как уже получившую приглашение.
    Используется в момент `join`, когда ссылка уже есть и показана в ответе."""
    await session.execute(
        update(EventParticipant)
        .where(EventParticipant.event_id == event_id)
        .where(EventParticipant.user_id == user_id)
        .values(chat_invite_notified=True),
    )


async def mark_response_notified(
    session: AsyncSession,
    *,
    seeking_id: int,
    user_id: int,
) -> None:
    await session.execute(
        update(CompanySeekingResponse)
        .where(CompanySeekingResponse.seeking_id == seeking_id)
        .where(CompanySeekingResponse.user_id == user_id)
        .values(chat_invite_notified=True),
    )
