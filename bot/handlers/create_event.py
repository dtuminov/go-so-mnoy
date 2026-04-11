from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MOSCOW_CITY_ID
from bot.keyboards.main_menu import main_menu_reply
from bot.services.events import create_event_draft
from bot.services.users import upsert_user_from_message
from bot.utils.datetime_parse import parse_user_datetime_msk

router = Router(name="create_event")


class CreateEventSG(StatesGroup):
    title = State()
    description = State()
    starts_at = State()
    place = State()


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
    await message.answer("Шаг 2/4: <b>описание</b> (можно одним сообщением).")


@router.message(CreateEventSG.description, F.text)
async def create_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if len(desc) < 5:
        await message.answer("Добавь чуть больше деталей в описание (от 5 символов).")
        return
    await state.update_data(description=desc[:4000])
    await state.set_state(CreateEventSG.starts_at)
    await message.answer(
        "Шаг 3/4: <b>дата и время начала</b> (Москва).\n"
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
    await message.answer("Шаг 4/4: <b>место</b> (адрес, район или «узнаем в чате»).")


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
    data = await state.get_data()
    title = data.get("title")
    description = data.get("description")
    starts_raw = data.get("starts_at_iso")
    if not title or not description or not starts_raw:
        await state.clear()
        await message.answer("Что-то пошло не так с черновиком. Начни снова: «➕ Создать событие».")
        return

    starts_at = datetime.fromisoformat(starts_raw)
    user = await upsert_user_from_message(session, message)
    await create_event_draft(
        session,
        organizer_id=user.id,
        city_id=MOSCOW_CITY_ID,
        title=title,
        description=description,
        starts_at=starts_at,
        place_text=place[:500],
    )
    await state.clear()
    await message.answer(
        "Событие отправлено на <b>ручную проверку</b>. После модерации оно появится в ленте.",
        reply_markup=main_menu_reply(),
    )
