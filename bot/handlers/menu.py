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
from bot.models import User
from bot.services.company_seeking import (
    get_user_responded_seekings,
    get_user_seekings,
    remove_user_response,
)
from bot.services.event_feed import build_event_feed_view
from bot.services.events import get_user_joined_events, get_user_organized_events
from bot.services.search_prefs import get_event_tag_filter, get_seeking_tag_filter
from bot.services.users import is_profile_complete, upsert_telegram_user, upsert_user_from_message
from bot.utils.formatting import esc, format_datetime_msk

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


async def _build_profile_view(
    session: AsyncSession,
    user: User,
) -> tuple[str, InlineKeyboardMarkup]:
    """Собирает caption и клавиатуру для карточки профиля.

    Вынесено из `on_my_profile`, чтобы можно было перерисовывать профиль
    в хэндлерах, меняющих вложенное состояние (например, отписка от
    отклика) — через `edit_caption` + `edit_reply_markup`.
    """
    name = esc(user.first_name or user.username or "Ты")
    lines = [f"<b>👤 {name}</b>", f"Возраст: {user.age}", "", esc(user.bio or "")]
    inline_rows: list[list[InlineKeyboardButton]] = []

    # Записи (участник)
    joined = await get_user_joined_events(session, user_id=user.id)
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
            chat_mark = " · 💬" if ev.chat_url else ""
            lines.append(
                f"{status_icon} {esc(ev.title)}{chat_mark} — {format_datetime_msk(ev.starts_at)}"
            )
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"👥 Участники: {esc(ev.title[:20])}",
                    callback_data=f"ep:{ev.id}",
                ),
                InlineKeyboardButton(
                    text="🚫 Отменить",
                    callback_data=f"ecancel:{ev.id}",
                ),
            ])
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"💬 Чат: {esc(ev.title[:24])}",
                    callback_data=f"evch:show:{ev.id}",
                ),
            ])

    # Мои отклики на чужие заявки
    responded = await get_user_responded_seekings(session, user_id=user.id)
    if responded:
        lines += ["", "<b>Мои отклики:</b>"]
        for sk in responded:
            lines.append(f"• {esc(sk.title)}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"❌ Убрать отклик: {esc(sk.title[:24])}",
                    callback_data=f"srd:{sk.id}",
                ),
            ])

    # Мои заявки «ищу компанию» (как автор)
    seekings = await get_user_seekings(session, author_id=user.id)
    if seekings:
        lines += ["", "<b>Мои заявки:</b>"]
        for sk in seekings:
            status_icon = "✅" if sk.status == "published" else "🕐"
            chat_mark = " · 💬" if sk.chat_url else ""
            lines.append(f"{status_icon} {esc(sk.title)}{chat_mark}")
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
                InlineKeyboardButton(
                    text=f"💬 Чат: {esc(sk.title[:24])}",
                    callback_data=f"skch:show:{sk.id}",
                ),
            ])

    inline_rows.append([
        InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="profile:edit")
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=inline_rows)


@router.message(F.text == BTN_MY_PROFILE, StateFilter(default_state))
async def on_my_profile(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = await upsert_user_from_message(session, message)
    if not is_profile_complete(user):
        await begin_profile_flow(message, state, pending_event_id=None)
        return

    text, kb = await _build_profile_view(session, user)
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
    # Перерисовываем карточку профиля на месте, чтобы кнопка исчезла.
    text, kb = await _build_profile_view(session, user)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.edit_text(
                text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        # Сообщение могло устареть — не критично, при следующем открытии профиля обновится.
        pass


@router.message(F.text == BTN_CREATE_EVENT, StateFilter(default_state))
async def on_create_event_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateEventSG.title)
    await message.answer(
        "Создаём событие. Шаг 1/6: <b>название</b> (до 120 символов).\n"
        "Отмена: /cancel",
    )
