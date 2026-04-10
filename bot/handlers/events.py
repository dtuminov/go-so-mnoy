from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import EVENT_PUBLISHED
from bot.services.events import (
    count_participants,
    get_event,
    user_joined_event,
)
from bot.services.users import upsert_telegram_user
from bot.utils.formatting import esc, format_datetime_msk

router = Router(name="events")


@router.callback_query(F.data.startswith("e:"))
async def on_event_open(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        event_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return

    event = await get_event(session, event_id)
    if event is None or event.status != EVENT_PUBLISHED:
        await callback.answer("Событие недоступно", show_alert=True)
        return

    n = await count_participants(session, event_id)
    text = (
        f"<b>{esc(event.title)}</b>\n"
        f"{format_datetime_msk(event.starts_at)}\n"
        f"📍 {esc(event.place_text)}\n"
        f"👥 Участников: {n}\n\n"
        f"{esc(event.description)}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Иду ✅", callback_data=f"j:{event_id}")],
        ],
    )
    await callback.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("j:"))
async def on_event_join(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        event_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    event = await get_event(session, event_id)
    if event is None or event.status != EVENT_PUBLISHED:
        await callback.answer("Событие недоступно", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    joined = await user_joined_event(session, event_id=event_id, user_id=user.id)
    if joined:
        await callback.answer("Ты в списке участников!")
    else:
        await callback.answer("Ты уже записан на это событие.", show_alert=False)
