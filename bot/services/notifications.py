"""DM-уведомления о событиях в боте.

Собираем в одном месте отправку «к тебе кто-то присоединился» —
для events и seekings (после унификации это одна функция).
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import ACTIVITY_EVENT
from bot.models import Activity, User
from bot.utils.formatting import esc


def _build_member_card(
    *,
    member: User,
    activity: Activity,
    is_pending: bool,
) -> tuple[str, InlineKeyboardMarkup]:
    name = member.first_name or member.username or "Кто-то"
    username_part = f" (@{member.username})" if member.username else ""

    if is_pending:
        verb = "хочет вступить в"
    elif activity.kind == ACTIVITY_EVENT:
        verb = "записался на"
    else:
        verb = "откликнулся на"

    entity = "событие" if activity.kind == ACTIVITY_EVENT else "заявку"
    headline = (
        f"🙋 <b>{esc(name)}{esc(username_part)}</b> {verb} "
        f"{entity} «{esc(activity.title)}»."
    )

    text = (
        f"{headline}\n"
        f"Возраст: {member.age or '—'}\n"
        f"О себе: {esc(member.bio or '—')}"
    )

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"💬 Написать {esc(name)}",
                url=f"tg://user?id={member.telegram_id}",
            ),
        ],
    ]
    if is_pending:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"amap:{activity.id}:{member.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"amrj:{activity.id}:{member.id}",
                ),
            ],
        )

    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def notify_creator_about_new_member(
    bot: Bot,
    *,
    recipient_tg_id: int,
    member: User,
    activity: Activity,
    is_pending: bool,
) -> None:
    """Шлёт organizer/author DM с профилем нового участника.

    Если `is_pending=True` — сообщение оформляется как «хочет вступить»
    и в клавиатуре появляются кнопки ✅/❌ для подтверждения/отказа
    (callback `amap:` / `amrj:` обрабатывается в `handlers/activity.py`).

    Тихо игнорирует ошибки отправки (заблокировал бота, deactivated).
    """
    text, kb = _build_member_card(
        member=member, activity=activity, is_pending=is_pending,
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


async def notify_user_about_decision(
    bot: Bot,
    *,
    recipient_tg_id: int,
    activity: Activity,
    approved: bool,
    chat_url: str | None = None,
) -> None:
    """Уведомляет пользователя о решении организатора по его pending-заявке."""
    entity = "событие" if activity.kind == ACTIVITY_EVENT else "заявку"
    if approved:
        text = (
            f"✅ Организатор подтвердил твою заявку на {entity} "
            f"«<b>{esc(activity.title)}</b>». Ты в списке участников!"
        )
        kb: InlineKeyboardMarkup | None = None
        if chat_url:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Открыть чат", url=chat_url)],
                ],
            )
    else:
        text = (
            f"😔 Организатор отклонил твою заявку на {entity} "
            f"«<b>{esc(activity.title)}</b>». "
            "Ты можешь подать заявку снова, если что-то изменится."
        )
        kb = None
    try:
        await bot.send_message(
            recipient_tg_id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception:
        pass


async def notify_members_about_cancel(
    bot: Bot,
    *,
    activity: Activity,
    members: list[tuple[int, str]],  # (telegram_id, status)
) -> None:
    """Шлёт уведомление об отмене события и joined, и pending членам."""
    entity = "Событие" if activity.kind == ACTIVITY_EVENT else "Заявка"
    text = (
        f"🚫 {entity} «<b>{esc(activity.title)}</b>» отменено организатором."
    )
    for tg_id, _status in members:
        try:
            await bot.send_message(
                tg_id,
                text,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
