from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, ACTIVITY_PUBLISHED, ACTIVITY_SEEKING
from bot.keyboards.activity_feed import format_activity_card_text
from bot.keyboards.main_menu import main_menu_reply
from bot.services.activities import (
    count_joined_members,
    get_activity,
    get_creator_summary,
)
from bot.services.users import upsert_user_from_message

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

    # Канонический формат ссылки после унификации.
    if args.startswith("act_"):
        try:
            activity_id = int(args.removeprefix("act_").strip())
        except ValueError:
            await message.answer(
                "Не понял ссылку. Открываю меню.", reply_markup=main_menu_reply(),
            )
            return
        activity = await get_activity(session, activity_id)
        if activity is None or activity.status != ACTIVITY_PUBLISHED:
            await message.answer(
                "Уже недоступно. Загляни в ленту.",
                reply_markup=main_menu_reply(),
            )
            return
        members = await count_joined_members(session, activity_id)
        author_name = author_age = None
        if activity.kind == ACTIVITY_SEEKING:
            author_name, author_age = await get_creator_summary(session, activity)
        text = format_activity_card_text(
            activity,
            members=members,
            author_name=author_name,
            author_age=author_age,
        )
        section = (
            "📍 Найти событие" if activity.kind == ACTIVITY_EVENT else "🤝 Найти компанию"
        )
        await message.answer(
            text + f"\n\nОткрой раздел «{section}» и нажми «Иду» / «Хочу», чтобы записаться.",
            reply_markup=main_menu_reply(),
        )
        return

    # Старые форматы из уже опубликованных постов канала: id'ы старых
    # таблиц после миграции 007 не сохранились, поэтому честно говорим
    # «устарело».
    if args.startswith("event_") or args.startswith("seek_"):
        await message.answer(
            "Ссылка из старых постов устарела. Открой раздел в меню — там актуальная лента.",
            reply_markup=main_menu_reply(),
        )
        return

    await message.answer(
        "Привет! Выбери действие в меню ниже — до встречи пара кликов.",
        reply_markup=main_menu_reply(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды: /start — меню и ссылки из канала, /help — эта справка, "
        "/cancel — отменить создание.",
    )
