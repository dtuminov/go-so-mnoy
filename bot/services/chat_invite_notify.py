"""Рассылка ссылки на чат участникам активности.

Логика:
- При первом заполнении `Activity.chat_url` (NULL → value) вызывающий код
  вызывает `broadcast_chat_invite`. Рассылаем только тем, у кого
  `chat_invite_notified=false` И `status='joined'`. По успеху ставим флаг.
- Pending-членам приглашение **не шлём** — они узнают о чате после
  approve.
- Ошибки доставки (юзер заблокировал бота, deactivated) глотаем —
  флаг всё равно ставим.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, MEMBER_JOINED
from bot.models import Activity, ActivityMember, User
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


async def broadcast_chat_invite(
    session: AsyncSession,
    bot: Bot,
    *,
    activity: Activity,
) -> int:
    """Шлёт всем joined-членам приглашение в чат. Возвращает количество
    адресатов до начала рассылки."""
    if not activity.chat_url:
        return 0

    stmt = (
        select(ActivityMember, User)
        .join(User, User.id == ActivityMember.user_id)
        .where(ActivityMember.activity_id == activity.id)
        .where(ActivityMember.status == MEMBER_JOINED)
        .where(ActivityMember.chat_invite_notified.is_(False))
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return 0

    if activity.kind == ACTIVITY_EVENT:
        text = (
            f"🎉 Организатор события «<b>{esc(activity.title)}</b>» добавил чат.\n"
            "Заходи, чтобы обсудить детали!"
        )
    else:
        text = (
            f"🎉 Автор заявки «<b>{esc(activity.title)}</b>» добавил чат.\n"
            "Заходи, чтобы обсудить детали!"
        )

    member_ids: list[int] = []
    for member, user in rows:
        await _send_invite(
            bot, tg_id=user.telegram_id, text=text, chat_url=activity.chat_url,
        )
        member_ids.append(member.id)

    await session.execute(
        update(ActivityMember)
        .where(ActivityMember.id.in_(member_ids))
        .values(chat_invite_notified=True),
    )
    return len(member_ids)


async def mark_member_notified(
    session: AsyncSession,
    *,
    activity_id: int,
    user_id: int,
) -> None:
    """Помечает запись участника как уже получившую приглашение.
    Используется в момент мгновенного join, когда ссылка уже есть и
    показана сразу."""
    await session.execute(
        update(ActivityMember)
        .where(ActivityMember.activity_id == activity_id)
        .where(ActivityMember.user_id == user_id)
        .values(chat_invite_notified=True),
    )
