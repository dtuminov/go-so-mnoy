from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MOSCOW_CITY_ID
from bot.handlers.create_event import CreateEventSG
from bot.keyboards.main_menu import BTN_CREATE_EVENT, BTN_FIND_COMPANY, BTN_FIND_EVENTS
from bot.services.events import list_published_events
from bot.utils.formatting import esc, format_datetime_msk

router = Router(name="menu")


@router.message(F.text == BTN_FIND_EVENTS, StateFilter(default_state))
async def on_find_events(message: Message, session: AsyncSession) -> None:
    events = await list_published_events(session, city_id=MOSCOW_CITY_ID, limit=12)
    if not events:
        await message.answer(
            "Пока нет опубликованных событий в Москве. Загляни позже или создай своё — «➕ Создать событие».",
        )
        return

    lines = ["<b>События в Москве</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for ev in events:
        lines.append(
            f"• <b>{esc(ev.title)}</b> — {format_datetime_msk(ev.starts_at)}",
        )
        short = ev.title if len(ev.title) <= 28 else ev.title[:27] + "…"
        buttons.append(
            [InlineKeyboardButton(text=f"📍 {short}", callback_data=f"e:{ev.id}")],
        )

    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == BTN_FIND_COMPANY, StateFilter(default_state))
async def on_find_company(message: Message) -> None:
    await message.answer(
        "Раздел «ищу компанию» в разработке: отдельные заявки и отклики появятся следующим шагом.",
    )


@router.message(F.text == BTN_CREATE_EVENT, StateFilter(default_state))
async def on_create_event_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEventSG.title)
    await message.answer(
        "Создаём событие. Шаг 1/4: <b>название</b> (до 120 символов).\n"
        "Отмена: /cancel",
    )
