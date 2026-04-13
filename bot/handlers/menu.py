from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, ACTIVITY_SEEKING
from bot.handlers.activity_create import start_create_activity
from bot.handlers.profile import ProfileSG, begin_profile_flow
from bot.keyboards.main_menu import (
    BTN_CREATE_ACTIVITY,
    BTN_FIND_COMPANY,
    BTN_FIND_EVENTS,
    BTN_MY_PROFILE,
)
from bot.services.activity_feed import build_activity_feed_view
from bot.services.cover import send_activity_cover
from bot.services.profile_view import build_hub_view
from bot.services.search_prefs import (
    get_event_tag_filter,
    get_filter_city_id,
    get_seeking_tag_filter,
)
from bot.services.users import is_profile_complete, upsert_user_from_message

router = Router(name="menu")



@router.message(F.text == BTN_FIND_EVENTS)
async def on_find_events(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await upsert_user_from_message(session, message)
    ids = get_event_tag_filter(user)
    filter_city_id = get_filter_city_id(user)
    city_id = filter_city_id if filter_city_id is not None else user.city_id
    from bot.models import City
    city = await session.get(City, city_id)
    city_name = city.name if city else ""
    view = await build_activity_feed_view(
        session,
        kind=ACTIVITY_EVENT,
        index=0,
        city_id=city_id,
        city_name=city_name,
        tag_ids=ids or None,
        viewer_user_id=user.id,
    )
    if view is None:
        filter_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Фильтры", callback_data="tp:e:open")],
        ])
        await message.answer(
            f"Пока нет событий ({city_name}).\n"
            "Попробуй другой город через фильтры или создай своё.",
            reply_markup=filter_kb,
        )
        return
    cover_file_id, text, kb = view
    await send_activity_cover(
        message, cover_file_id=cover_file_id, caption=text, reply_markup=kb,
    )


@router.message(F.text == BTN_FIND_COMPANY)
async def on_find_company(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await upsert_user_from_message(session, message)
    ids = get_seeking_tag_filter(user)
    filter_city_id = get_filter_city_id(user)
    city_id = filter_city_id if filter_city_id is not None else user.city_id
    from bot.models import City
    city = await session.get(City, city_id)
    city_name = city.name if city else ""
    view = await build_activity_feed_view(
        session,
        kind=ACTIVITY_SEEKING,
        index=0,
        city_id=city_id,
        city_name=city_name,
        tag_ids=ids or None,
        viewer_user_id=user.id,
    )
    if view is None:
        filter_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Фильтры", callback_data="tp:s:open")],
        ])
        await message.answer(
            f"Пока нет заявок ({city_name}).\n"
            "Попробуй другой город через фильтры или создай своё.",
            reply_markup=filter_kb,
        )
        return
    cover_file_id, text, kb = view
    await send_activity_cover(
        message, cover_file_id=cover_file_id, caption=text, reply_markup=kb,
    )


@router.message(F.text == BTN_MY_PROFILE)
async def on_my_profile(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
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


@router.message(F.text == BTN_CREATE_ACTIVITY)
async def on_create_activity_entry(message: Message, state: FSMContext) -> None:
    await state.clear()
    """Единая точка входа в создание активности — kind выбирается
    inline-кнопками внутри `start_create_activity`."""
    await start_create_activity(message, state)
