from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.company_seeking import CreateSeekingSG, build_feed_view
from bot.handlers.create_event import CreateEventSG
from bot.handlers.profile import ProfileSG, begin_profile_flow
from bot.keyboards.main_menu import BTN_CREATE_EVENT, BTN_FIND_COMPANY, BTN_FIND_EVENTS, BTN_MY_PROFILE
from bot.services.company_seeking import get_user_seekings
from bot.services.event_feed import build_event_feed_view
from bot.services.events import get_user_joined_events, get_user_organized_events
from bot.services.search_prefs import get_event_tag_filter, get_seeking_tag_filter
from bot.services.users import is_profile_complete, upsert_user_from_message
from bot.utils.formatting import esc, format_datetime_msk

router = Router(name="menu")


@router.message(F.text == BTN_FIND_EVENTS, StateFilter(default_state))
async def on_find_events(message: Message, session: AsyncSession) -> None:
    user = await upsert_user_from_message(session, message)
    ids = get_event_tag_filter(user)
    view = await build_event_feed_view(session, index=0, tag_ids=ids or None)
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
    view = await build_feed_view(session, 0, tag_ids=ids or None)
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

    name = esc(user.first_name or user.username or "Ты")
    lines = [f"<b>👤 {name}</b>", f"Возраст: {user.age}", "", esc(user.bio or "")]

    # Записи (участник)
    joined = await get_user_joined_events(session, user_id=user.id)
    inline_rows: list[list[InlineKeyboardButton]] = []
    if joined:
        lines += ["", "<b>Мои записи:</b>"]
        for ev in joined:
            lines.append(f"• {esc(ev.title)} — {format_datetime_msk(ev.starts_at)}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"❌ Отписаться: {esc(ev.title[:30])}",
                    callback_data=f"uleave:{ev.id}",
                )
            ])
    else:
        lines += ["", "Пока не записан ни на одно событие."]

    # Организованные события
    organized = await get_user_organized_events(session, user_id=user.id)
    if organized:
        lines += ["", "<b>Мои события (организатор):</b>"]
        for ev in organized:
            status_icon = "✅" if ev.status == "published" else "🕐"
            lines.append(f"{status_icon} {esc(ev.title)} — {format_datetime_msk(ev.starts_at)}")
            row = [
                InlineKeyboardButton(
                    text=f"👥 Участники: {esc(ev.title[:20])}",
                    callback_data=f"ep:{ev.id}",
                ),
                InlineKeyboardButton(
                    text="🚫 Отменить",
                    callback_data=f"ecancel:{ev.id}",
                ),
            ]
            inline_rows.append(row)

    # Заявки «ищу компанию»
    seekings = await get_user_seekings(session, author_id=user.id)
    if seekings:
        lines += ["", "<b>Мои заявки:</b>"]
        for sk in seekings:
            status_icon = "✅" if sk.status == "published" else "🕐"
            lines.append(f"{status_icon} {esc(sk.title)}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"👥 Отклики: {esc(sk.title[:20])}",
                    callback_data=f"skp:{sk.id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Закрыть",
                    callback_data=f"sk:close:{sk.id}",
                ),
            ])

    inline_rows.append([
        InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="profile:edit")
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)
    text = "\n".join(lines)

    await message.answer_photo(
        user.avatar_file_id,
        caption=text,
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == BTN_CREATE_EVENT, StateFilter(default_state))
async def on_create_event_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEventSG.title)
    await message.answer(
        "Создаём событие. Шаг 1/5: <b>название</b> (до 120 символов).\n"
        "Отмена: /cancel",
    )
