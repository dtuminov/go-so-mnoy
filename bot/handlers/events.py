from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import EVENT_PUBLISHED
from bot.handlers.create_event import CreateEventSG
from bot.handlers.profile import ProfileSG, begin_profile_flow
from bot.keyboards.events_feed import format_event_card_text
from bot.services.event_feed import build_event_feed_view
from bot.services.events import (
    cancel_event,
    count_participants,
    get_event,
    get_event_participants,
    leave_event,
    list_published_events,
    user_joined_event,
)
from bot.services.search_prefs import get_event_tag_filter
from bot.services.users import is_profile_complete, upsert_telegram_user
from bot.utils.formatting import esc

router = Router(name="events")


@router.callback_query(F.data.startswith("evp:g:"))
async def on_event_feed_page(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    try:
        idx = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_event_tag_filter(user)
    view = await build_event_feed_view(session, index=idx, tag_ids=ids or None)
    if view is None:
        await callback.answer("Событий больше нет", show_alert=True)
        return
    text, kb = view
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("evp:c:"))
async def on_event_feed_counter(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        idx = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_event_tag_filter(user)
    events = await list_published_events(session, tag_ids=ids or None)
    if not events:
        await callback.answer()
        return
    idx = max(0, min(idx, len(events) - 1))
    await callback.answer(f"{idx + 1} из {len(events)}", show_alert=True)


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
    text = format_event_card_text(event, participants=n)
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
async def on_event_join(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
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

    current = await state.get_state()
    if current is not None and current.startswith(CreateEventSG.__name__):
        await callback.answer(
            "Сначала заверши или отмени создание события: /cancel",
            show_alert=True,
        )
        return
    if current is not None and current.startswith(ProfileSG.__name__):
        # Явно перезаписываем оба ключа: событие — новое, заявку — сбрасываем.
        # Иначе если до этого был pending_seek_id, после анкеты запишут туда тоже.
        await state.update_data({"pending_join_event_id": event_id, "pending_seek_id": None})
        await callback.answer(
            "Ок — после анкеты запишем на это событие.",
            show_alert=False,
        )
        return

    user = await upsert_telegram_user(session, callback.from_user)
    if not is_profile_complete(user):
        await begin_profile_flow(
            callback.message,
            state,
            pending_event_id=event_id,
            event_title=event.title,
        )
        await callback.answer("Сначала анкета в чате 👇")
        return

    joined = await user_joined_event(session, event_id=event_id, user_id=user.id)
    if joined:
        await callback.answer("Ты в списке участников!")
        # Обновляем карточку — добавляем кнопку «Отписаться»
        n = await count_participants(session, event_id)
        text = format_event_card_text(event, participants=n)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отписаться", callback_data=f"uleave:{event_id}")],
            ]
        )
        if callback.message:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await callback.answer("Ты уже записан на это событие.", show_alert=False)


@router.callback_query(F.data.startswith("uleave:"))
async def on_event_leave(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        event_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    removed = await leave_event(session, event_id=event_id, user_id=user.id)
    if removed:
        await callback.answer("Ты отписался от события.")
        event = await get_event(session, event_id)
        if event:
            n = await count_participants(session, event_id)
            text = format_event_card_text(event, participants=n)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Иду ✅", callback_data=f"j:{event_id}")],
                ]
            )
            await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await callback.answer("Ты не был записан.", show_alert=False)


@router.callback_query(F.data.startswith("ep:"))
async def on_event_participants(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        event_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    event = await get_event(session, event_id)
    if event is None:
        await callback.answer("Событие не найдено", show_alert=True)
        return
    if event.organizer_id != (await upsert_telegram_user(session, callback.from_user)).id:
        await callback.answer("Только организатор может смотреть список.", show_alert=True)
        return

    rows = await get_event_participants(session, event_id=event_id)
    if not rows:
        await callback.answer("Пока никто не записался.", show_alert=True)
        return

    lines = [f"<b>Участники «{esc(event.title)}»:</b>"]
    for i, (_, u) in enumerate(rows, 1):
        name = esc(u.first_name or u.username or "—")
        username_part = f" @{esc(u.username)}" if u.username else ""
        age_part = f", {u.age} лет" if u.age else ""
        bio_part = f"\n   {esc((u.bio or '')[:80])}" if u.bio else ""
        lines.append(f"{i}. {name}{username_part}{age_part}{bio_part}")

    await callback.message.answer("\n".join(lines), parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("ecancel:"))
async def on_event_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        event_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    cancelled = await cancel_event(session, event_id=event_id, organizer_id=user.id)
    if cancelled:
        await callback.answer("Событие отменено.", show_alert=False)
        await callback.message.edit_text(
            (callback.message.text or "") + "\n\n<i>🚫 Отменено</i>",
            reply_markup=None,
            parse_mode=ParseMode.HTML,
        )
    else:
        await callback.answer("Не удалось отменить — это не твоё событие.", show_alert=True)
