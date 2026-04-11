from datetime import datetime

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MOSCOW_CITY_ID
from bot.keyboards.main_menu import main_menu_reply
from bot.keyboards.tag_picker import tag_picker_keyboard
from bot.services.events import create_event_draft
from bot.services.tags import list_active_tags
from bot.services.users import upsert_user_from_message, upsert_telegram_user
from bot.utils.chat_link import InvalidChatLinkError, normalize_chat_link
from bot.utils.datetime_parse import parse_user_datetime_msk

router = Router(name="create_event")


class CreateEventSG(StatesGroup):
    title = State()
    description = State()
    starts_at = State()
    place = State()
    chat_url = State()
    tags = State()


CT_E_PREFIX = "ct:e"
CT_E_TMP_KEY = "create_event_tag_ids"
CE_CHAT_SKIP_CB = "cecu:skip"


def _chat_url_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data=CE_CHAT_SKIP_CB)],
        ],
    )


async def _render_tags_step(
    message: Message,
    session: AsyncSession,
    *,
    selected_ids: set[int],
) -> None:
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=selected_ids,
        prefix=CT_E_PREFIX,
        with_done=True,
    )
    await message.answer(
        "Шаг 6/6: <b>выбери теги</b> (минимум один). "
        "Нажми на тег, чтобы отметить, и «✅ Готово» когда выберешь.",
        reply_markup=kb,
    )


@router.message(Command("cancel"), StateFilter(CreateEventSG))
async def create_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Создание события отменено.", reply_markup=main_menu_reply())


@router.message(CreateEventSG.title, F.text)
async def create_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("Слишком коротко. Напиши название хотя бы из 3 символов.")
        return
    if len(title) > 120:
        title = title[:120]
    await state.update_data(title=title)
    await state.set_state(CreateEventSG.description)
    await message.answer("Шаг 2/6: <b>описание</b> (можно одним сообщением).")


@router.message(CreateEventSG.description, F.text)
async def create_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if len(desc) < 5:
        await message.answer("Добавь чуть больше деталей в описание (от 5 символов).")
        return
    await state.update_data(description=desc[:4000])
    await state.set_state(CreateEventSG.starts_at)
    await message.answer(
        "Шаг 3/6: <b>дата и время начала</b> (Москва).\n"
        "Примеры: <code>25.04.2026 19:00</code> или <code>2026-04-25 19:00</code>",
    )


@router.message(CreateEventSG.starts_at, F.text)
async def create_starts(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        starts_at = parse_user_datetime_msk(raw)
    except ValueError as e:
        await message.answer(str(e))
        return
    await state.update_data(starts_at_iso=starts_at.isoformat())
    await state.set_state(CreateEventSG.place)
    await message.answer("Шаг 4/6: <b>место</b> (адрес, район или «узнаем в чате»).")


@router.message(CreateEventSG.place, F.text)
async def create_place(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    place = (message.text or "").strip()
    if len(place) < 2:
        await message.answer("Укажи место чуть подробнее.")
        return
    await state.update_data(place_text=place[:500])
    await state.set_state(CreateEventSG.chat_url)
    await message.answer(
        "Шаг 5/6: <b>ссылка на чат события</b> (например, "
        "<code>https://t.me/...</code>) — чтобы участники сразу могли попасть в обсуждение.\n\n"
        "Можно пропустить и добавить позже в профиле.",
        reply_markup=_chat_url_prompt_kb(),
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateEventSG.chat_url, F.text)
async def create_chat_url(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    raw = message.text or ""
    try:
        link = normalize_chat_link(raw)
    except InvalidChatLinkError as e:
        await message.answer(
            str(e),
            reply_markup=_chat_url_prompt_kb(),
            parse_mode=ParseMode.HTML,
        )
        return
    await state.update_data(chat_url=link, **{CT_E_TMP_KEY: []})
    await state.set_state(CreateEventSG.tags)
    await _render_tags_step(message, session, selected_ids=set())


@router.callback_query(
    F.data == CE_CHAT_SKIP_CB,
    StateFilter(CreateEventSG.chat_url),
)
async def create_chat_url_skip(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await state.update_data(chat_url=None, **{CT_E_TMP_KEY: []})
    await state.set_state(CreateEventSG.tags)
    # Убираем кнопку «Пропустить» с предыдущего сообщения, чтобы не тыкали повторно.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _render_tags_step(callback.message, session, selected_ids=set())
    await callback.answer("Пропущено — можно добавить позже в профиле")


@router.callback_query(
    F.data.startswith(f"{CT_E_PREFIX}:t:"),
    StateFilter(CreateEventSG.tags),
)
async def create_tags_toggle(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    try:
        tag_id = int(callback.data.split(":", 3)[3])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    data = await state.get_data()
    current = set(data.get(CT_E_TMP_KEY) or [])
    if tag_id in current:
        current.remove(tag_id)
    else:
        current.add(tag_id)
    await state.update_data({CT_E_TMP_KEY: sorted(current)})
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=current,
        prefix=CT_E_PREFIX,
        with_done=True,
    )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(
    F.data == f"{CT_E_PREFIX}:done",
    StateFilter(CreateEventSG.tags),
)
async def create_tags_done(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    tag_ids = list(data.get(CT_E_TMP_KEY) or [])
    if not tag_ids:
        await callback.answer("Выбери хотя бы один тег", show_alert=True)
        return

    title = data.get("title")
    description = data.get("description")
    starts_raw = data.get("starts_at_iso")
    place_text = data.get("place_text")
    chat_url = data.get("chat_url")  # может быть None — это нормально
    if not title or not description or not starts_raw or not place_text:
        await state.clear()
        await callback.message.answer(
            "Что-то пошло не так с черновиком. Начни снова: «➕ Создать событие».",
            reply_markup=main_menu_reply(),
        )
        await callback.answer()
        return

    starts_at = datetime.fromisoformat(starts_raw)
    user = await upsert_telegram_user(session, callback.from_user)
    await create_event_draft(
        session,
        organizer_id=user.id,
        city_id=MOSCOW_CITY_ID,
        title=title,
        description=description,
        starts_at=starts_at,
        place_text=place_text,
        chat_url=chat_url,
        tag_ids=tag_ids,
    )
    await state.clear()
    await callback.message.answer(
        "Событие отправлено на <b>ручную проверку</b>. После модерации оно появится в ленте.",
        reply_markup=main_menu_reply(),
    )
    await callback.answer()
