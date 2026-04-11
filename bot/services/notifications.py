"""DM-уведомления о событиях в боте.

Собираем в одном месте отправку «тебе кто-то присоединился» —
симметрично для записи на событие и отклика на заявку.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.models import User
from bot.utils.formatting import esc


def _build_member_card(
    *,
    member: User,
    entity_title: str,
    entity_kind: str,
) -> tuple[str, InlineKeyboardMarkup]:
    name = member.first_name or member.username or "Кто-то"
    username_part = f" (@{member.username})" if member.username else ""

    if entity_kind == "event":
        headline = (
            f"🎉 <b>{esc(name)}{esc(username_part)}</b> записался "
            f"на твоё событие «{esc(entity_title)}»."
        )
    else:  # "seeking"
        headline = (
            f"🙋 <b>{esc(name)}{esc(username_part)}</b> откликнулся "
            f"на твою заявку «{esc(entity_title)}»."
        )

    text = (
        f"{headline}\n"
        f"Возраст: {member.age or '—'}\n"
        f"О себе: {esc(member.bio or '—')}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💬 Написать {esc(name)}",
                    url=f"tg://user?id={member.telegram_id}",
                ),
            ],
        ],
    )
    return text, kb


async def notify_actor_about_new_member(
    bot: Bot,
    *,
    recipient_tg_id: int,
    member: User,
    entity_title: str,
    entity_kind: str,  # "event" | "seeking"
) -> None:
    """Шлёт автору/организатору сообщение с профилем нового участника.

    Тихо игнорирует любые ошибки отправки (юзер заблокировал бота,
    аккаунт удалён и т.п.) — это не должно валить основной флоу.
    """
    text, kb = _build_member_card(
        member=member,
        entity_title=entity_title,
        entity_kind=entity_kind,
    )
    try:
        if member.avatar_file_id:
            await bot.send_photo(
                recipient_tg_id,
                photo=member.avatar_file_id,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                recipient_tg_id,
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
    except Exception:
        pass
