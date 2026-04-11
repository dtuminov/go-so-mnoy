from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.company_seeking import CreateSeekingSG, build_feed_view
from bot.handlers.create_event import CreateEventSG
from bot.handlers.profile import ProfileSG, begin_profile_flow
from bot.keyboards.main_menu import BTN_CREATE_EVENT, BTN_FIND_COMPANY, BTN_FIND_EVENTS, BTN_MY_PROFILE
from bot.services.company_seeking import remove_user_response
from bot.services.event_feed import build_event_feed_view
from bot.services.profile_view import build_profile_view, rerender_profile_card
from bot.services.search_prefs import get_event_tag_filter, get_seeking_tag_filter
from bot.services.users import is_profile_complete, upsert_telegram_user, upsert_user_from_message

router = Router(name="menu")


@router.message(F.text == BTN_FIND_EVENTS, StateFilter(default_state))
async def on_find_events(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_message(session, message)
    ids = get_event_tag_filter(user)
    view = await build_event_feed_view(
        session, index=0, tag_ids=ids or None, viewer_user_id=user.id,
    )
    if view is None:
        hint = (
            "По выбранным тегам событий нет. Нажми «🔎 Фильтры» в ленте и сбрось."
            if ids
            else "Пока нет опубликованных событий в Москве. Загляни позже или создай своё — «➕ Создать событие»."
        )
        await message.answer(hint)
        return
    text, kb = view
    await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(F.text == BTN_FIND_COMPANY, StateFilter(default_state))
async def on_find_company(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_message(session, message)
    ids = get_seeking_tag_filter(user)
    view = await build_feed_view(
        session, 0, tag_ids=ids or None, viewer_user_id=user.id,
    )
    if view is None:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Предложить своё", callback_data="sk:create")]
            ]
        )
        await message.answer(
            "Пока нет активных заявок в Москве. Будь первым — предложи своё!",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return
    text, kb = view
    await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(F.text == BTN_MY_PROFILE, StateFilter(default_state))
async def on_my_profile(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await upsert_user_from_message(session, message)
    if not is_profile_complete(user):
        await begin_profile_flow(message, state, pending_event_id=None)
        return

    text, kb = await build_profile_view(session, user)
    await message.answer_photo(
        user.avatar_file_id,
        caption=text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("srd:"))
async def on_remove_response(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        seeking_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    removed = await remove_user_response(
        session, seeking_id=seeking_id, user_id=user.id,
    )
    if not removed:
        await callback.answer("Отклика уже нет.", show_alert=False)
        return

    await callback.answer("Отклик убран.")
    await rerender_profile_card(callback.message, session, user)


@router.message(F.text == BTN_CREATE_EVENT, StateFilter(default_state))
async def on_create_event_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEventSG.title)
    await message.answer(
        "Создаём событие. Шаг 1/6: <b>название</b> (до 120 символов).\n"
        "Отмена: /cancel",
    )
