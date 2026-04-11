from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, ACTIVITY_SEEKING
from bot.handlers.activity_create import start_create_activity
from bot.handlers.profile import begin_profile_flow
from bot.keyboards.main_menu import (
    BTN_CREATE_ACTIVITY,
    BTN_FIND_COMPANY,
    BTN_FIND_EVENTS,
    BTN_MY_PROFILE,
)
from bot.services.activity_feed import build_activity_feed_view
from bot.services.profile_view import build_hub_view
from bot.services.search_prefs import (
    get_event_tag_filter,
    get_seeking_tag_filter,
)
from bot.services.users import is_profile_complete, upsert_user_from_message

router = Router(name="menu")


def _filter_reset_kb(reset_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Сбросить фильтр", callback_data=reset_callback)],
        ],
    )


@router.message(F.text == BTN_FIND_EVENTS, StateFilter(default_state))
async def on_find_events(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_message(session, message)
    ids = get_event_tag_filter(user)
    view = await build_activity_feed_view(
        session,
        kind=ACTIVITY_EVENT,
        index=0,
        tag_ids=ids or None,
        viewer_user_id=user.id,
    )
    if view is None:
        if ids:
            await message.answer(
                "По выбранным тегам событий нет. Сбрось фильтр, чтобы посмотреть всё.",
                reply_markup=_filter_reset_kb("tp:e:reset"),
            )
        else:
            await message.answer(
                "Пока нет опубликованных событий в Москве. "
                "Загляни позже или создай своё.",
            )
        return
    text, kb = view
    await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(F.text == BTN_FIND_COMPANY, StateFilter(default_state))
async def on_find_company(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_message(session, message)
    ids = get_seeking_tag_filter(user)
    view = await build_activity_feed_view(
        session,
        kind=ACTIVITY_SEEKING,
        index=0,
        tag_ids=ids or None,
        viewer_user_id=user.id,
    )
    if view is None:
        if ids:
            await message.answer(
                "По выбранным тегам активных заявок нет. "
                "Сбрось фильтр, чтобы посмотреть всё.",
                reply_markup=_filter_reset_kb("tp:s:reset"),
            )
        else:
            await message.answer(
                "Пока нет активных заявок в Москве. Будь первым — нажми «➕ Ищу компанию»!",
            )
        return
    text, kb = view
    await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(F.text == BTN_MY_PROFILE, StateFilter(default_state))
async def on_my_profile(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await upsert_user_from_message(session, message)
    if not is_profile_complete(user):
        await begin_profile_flow(message, state)
        return

    text, kb = await build_hub_view(session, user)
    await message.answer_photo(
        user.avatar_file_id,
        caption=text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == BTN_CREATE_ACTIVITY, StateFilter(default_state))
async def on_create_activity_entry(message: Message, state: FSMContext) -> None:
    """Единая точка входа в создание активности — kind выбирается
    inline-кнопками внутри `start_create_activity`."""
    await start_create_activity(message, state)
