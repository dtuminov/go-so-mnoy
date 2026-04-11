from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import EVENT_PUBLISHED
from bot.keyboards.main_menu import main_menu_reply
from bot.services.events import get_event
from bot.services.users import upsert_user_from_message
from bot.utils.formatting import esc, format_datetime_msk

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    await upsert_user_from_message(session, message)
    args = (command.args or "").strip()

    if args.startswith("event_"):
        try:
            event_id = int(args.removeprefix("event_").strip())
        except ValueError:
            await message.answer("Не понял ссылку на событие. Открываю меню.", reply_markup=main_menu_reply())
            return
        event = await get_event(session, event_id)
        if event is None or event.status != EVENT_PUBLISHED:
            await message.answer("Событие не найдено или ещё не опубликовано.", reply_markup=main_menu_reply())
            return
        text = (
            f"<b>{esc(event.title)}</b>\n"
            f"{format_datetime_msk(event.starts_at)}\n"
            f"{esc(event.place_text)}\n\n"
            f"{esc(event.description)}"
        )
        await message.answer(
            text + "\n\nНажми «📍 Найти событие» → открой карточку → «Иду», чтобы записаться.",
            reply_markup=main_menu_reply(),
        )
        return

    if args.startswith("seek_"):
        await message.answer(
            "Заявки «ищу компанию» скоро здесь же. Пока загляни в «🤝 Найти компанию».",
            reply_markup=main_menu_reply(),
        )
        return

    await message.answer(
        "Привет! Выбери действие в меню ниже — до события пара кликов.",
        reply_markup=main_menu_reply(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды: /start — меню и ссылки из канала, /help — эта справка, "
        "/cancel — отменить создание события.",
    )
