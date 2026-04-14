from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, ACTIVITY_PUBLISHED
from bot.keyboards.main_menu import MENU_BUTTONS, main_menu_reply
from bot.services.activities import get_activity, join_activity
from bot.services.cities import search_cities
from bot.services.search_prefs import set_filter_city
from bot.services.users import (
    set_user_city,
    update_user_profile,
    upsert_telegram_user,
    upsert_user_from_message,
)
from bot.utils.formatting import esc

router = Router(name="profile")

PENDING_ACTIVITY_KEY = "pending_join_activity_id"
CB_EDIT_PROFILE = "profile:edit"


class ProfileSG(StatesGroup):
    edit_choice = State()
    city = State()
    avatar = State()
    age = State()
    bio = State()


def _city_step_text(*, activity_title: str | None, editing: bool = False) -> str:
    if editing:
        prefix = "Обновляем анкету.\n\n"
    elif activity_title:
        prefix = f"«{esc(activity_title)}» — после анкеты подадим заявку автоматически.\n\n"
    else:
        prefix = "Чтобы участвовать во встречах, заполни <b>анкету</b>.\n\n"
    return (
        prefix
        + "<b>Шаг 1/4</b>: отправь геолокацию или напиши название <b>города</b>.\n"
        "Отмена: /cancel"
    )


def _city_location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _city_results_keyboard(cities: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=c.name, callback_data=f"prf_city:{c.id}")]
        for c in cities
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def begin_profile_flow(
    target_message: Message,
    state: FSMContext,
    *,
    pending_event_id: int | None = None,
    pending_seeking_id: int | None = None,
    activity_title: str | None = None,
    editing: bool = False,
) -> None:
    """Стартует FSM анкеты. Первый шаг — выбор города."""
    await state.clear()
    await state.set_state(ProfileSG.city)
    data: dict = {"editing": editing}
    pending = pending_event_id if pending_event_id is not None else pending_seeking_id
    if pending is not None:
        data[PENDING_ACTIVITY_KEY] = pending
    await state.update_data(data)
    await target_message.answer(
        _city_step_text(activity_title=activity_title, editing=editing),
        parse_mode=ParseMode.HTML,
        reply_markup=_city_location_keyboard(),
    )


# ── edit callback (из карточки профиля) ──────────────────────────────────────


def _edit_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📍 Город", callback_data="pedit:city"),
            InlineKeyboardButton(text="📷 Фото", callback_data="pedit:avatar"),
        ],
        [
            InlineKeyboardButton(text="🔢 Возраст", callback_data="pedit:age"),
            InlineKeyboardButton(text="📝 О себе", callback_data="pedit:bio"),
        ],
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="pedit:cancel")],
    ])


@router.callback_query(F.data == CB_EDIT_PROFILE)
async def on_edit_profile_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await state.clear()
    await state.set_state(ProfileSG.edit_choice)
    await state.update_data(editing=True)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption="<b>Что хочешь изменить?</b>",
                reply_markup=_edit_choice_keyboard(),
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.edit_text(
                "<b>Что хочешь изменить?</b>",
                reply_markup=_edit_choice_keyboard(),
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "pedit:cancel", StateFilter(ProfileSG.edit_choice))
async def on_edit_cancel(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    # Возвращаемся в хаб профиля
    from bot.services.profile_view import rerender_profile_to_hub
    user = await upsert_telegram_user(session, callback.from_user)
    await rerender_profile_to_hub(callback.message, session, user)
    await callback.answer()


@router.callback_query(F.data == "pedit:city", StateFilter(ProfileSG.edit_choice))
async def on_edit_city(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileSG.city)
    await state.update_data(editing=True, edit_single="city")
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "Отправь геолокацию или напиши название города:",
        reply_markup=_city_location_keyboard(),
    )


@router.callback_query(F.data == "pedit:avatar", StateFilter(ProfileSG.edit_choice))
async def on_edit_avatar(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileSG.avatar)
    await state.update_data(editing=True, edit_single="avatar")
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "Отправь новое <b>фото</b> (как картинку, не файлом).\nОтмена: /cancel",
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "pedit:age", StateFilter(ProfileSG.edit_choice))
async def on_edit_age(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileSG.age)
    await state.update_data(editing=True, edit_single="age")
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "Напиши новый <b>возраст</b> числом (например, 24).\nОтмена: /cancel",
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "pedit:bio", StateFilter(ProfileSG.edit_choice))
async def on_edit_bio(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileSG.bio)
    await state.update_data(editing=True, edit_single="bio")
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "Напиши новый текст <b>о себе</b> (от 10 символов).\nОтмена: /cancel",
        parse_mode=ParseMode.HTML,
    )


# ── /cancel внутри анкеты ────────────────────────────────────────────────────


@router.message(Command("cancel"), StateFilter(ProfileSG))
async def profile_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    editing = data.get("editing", False)
    await state.clear()
    if editing:
        text = "Редактирование отменено — старые данные сохранены."
    else:
        text = "Анкета отменена. Когда будешь готов — снова нажми «Иду ✅»."
    await message.answer(text, reply_markup=main_menu_reply())


# ── шаги FSM ─────────────────────────────────────────────────────────────────


@router.message(ProfileSG.city, F.location)
async def profile_city_location(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    """Юзер отправил геолокацию — определяем город."""
    from bot.utils.geo import city_name_by_coords

    lat = message.location.latitude
    lon = message.location.longitude
    city_name = await city_name_by_coords(lat, lon)
    if not city_name:
        await message.answer(
            "Не удалось определить город по геолокации. Напиши название текстом.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    cities = await search_cities(session, city_name, limit=1)
    if not cities:
        await message.answer(
            f"Город «{city_name}» не найден в базе. Попробуй написать название текстом.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    city = cities[0]
    user = await upsert_user_from_message(session, message)
    await set_user_city(session, user_id=user.id, city_id=city.id)
    await set_filter_city(session, user=user, city_id=None)  # сброс фильтра
    data = await state.get_data()

    if data.get("edit_single") == "city":
        await state.clear()
        await message.answer(
            f"Город: {city.name} ✓",
            reply_markup=main_menu_reply(),
        )
        return

    await state.update_data(city_id=city.id)
    await state.set_state(ProfileSG.avatar)
    await message.answer(
        f"Город: {city.name} ✓\n\n"
        "<b>Шаг 2/4</b>: отправь <b>одно фото</b> (как картинку, не файлом).\n"
        "Отмена: /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_reply(),
    )


@router.message(ProfileSG.city, F.text, ~F.text.in_(MENU_BUTTONS))
async def profile_city_search(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("Напиши хотя бы 2 символа названия города.")
        return
    cities = await search_cities(session, query)
    if not cities:
        await message.answer(
            "Не нашёл такого города. Попробуй ещё раз — например, «Казань» или «Ново».",
        )
        return
    await message.answer(
        "Выбери свой город:",
        reply_markup=_city_results_keyboard(cities),
    )


@router.callback_query(F.data.startswith("prf_city:"), StateFilter(ProfileSG.city))
async def profile_city_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    try:
        city_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer()
        return

    user = await upsert_telegram_user(session, callback.from_user)
    await set_user_city(session, user_id=user.id, city_id=city_id)
    await set_filter_city(session, user=user, city_id=None)  # сброс фильтра
    data = await state.get_data()
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if data.get("edit_single") == "city":
        await state.clear()
        await callback.message.answer("Город обновлён.", reply_markup=main_menu_reply())
        return

    await state.update_data(city_id=city_id)
    await state.set_state(ProfileSG.avatar)
    await callback.message.answer(
        "<b>Шаг 2/4</b>: отправь <b>одно фото</b> (как картинку, не файлом).\n"
        "Отмена: /cancel",
        parse_mode=ParseMode.HTML,
    )


@router.message(ProfileSG.city)
async def profile_city_wrong(message: Message) -> None:
    await message.answer("Напиши название города текстом.")


@router.message(ProfileSG.avatar, F.photo)
async def profile_avatar(message: Message, state: FSMContext, session: AsyncSession) -> None:
    photos = message.photo
    if not photos:
        await message.answer("Пришли одно фото.")
        return
    file_id = photos[-1].file_id
    data = await state.get_data()

    if data.get("edit_single") == "avatar":
        user = await upsert_user_from_message(session, message)
        from sqlalchemy import update as sa_update
        from bot.models import User
        await session.execute(
            sa_update(User).where(User.id == user.id).values(avatar_file_id=file_id),
        )
        await state.clear()
        await message.answer("Фото обновлено.", reply_markup=main_menu_reply())
        return

    await state.update_data(avatar_file_id=file_id)
    await state.set_state(ProfileSG.age)
    await message.answer(
        "<b>Шаг 3/4</b>: напиши свой <b>возраст</b> одним числом (например, 24).",
        parse_mode=ParseMode.HTML,
    )


@router.message(ProfileSG.avatar)
async def profile_avatar_wrong(message: Message) -> None:
    await message.answer(
        "Сейчас нужно именно <b>фото</b>. Отправь одно изображение.",
        parse_mode=ParseMode.HTML,
    )


@router.message(ProfileSG.age, F.text)
async def profile_age(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    try:
        age = int(raw)
    except ValueError:
        await message.answer("Напиши возраст числом, например: 22")
        return
    if age < 14 or age > 99:
        await message.answer("Укажи возраст от 14 до 99.")
        return

    data = await state.get_data()
    if data.get("edit_single") == "age":
        user = await upsert_user_from_message(session, message)
        from sqlalchemy import update as sa_update
        from bot.models import User
        await session.execute(
            sa_update(User).where(User.id == user.id).values(age=age),
        )
        await state.clear()
        await message.answer("Возраст обновлён.", reply_markup=main_menu_reply())
        return

    await state.update_data(age=age)
    await state.set_state(ProfileSG.bio)
    await message.answer(
        "<b>Шаг 4/4</b>: <b>о себе</b> — от 10 символов: чем занимаешься, что любишь.",
        parse_mode=ParseMode.HTML,
    )


@router.message(ProfileSG.age)
async def profile_age_wrong(message: Message) -> None:
    await message.answer("Отправь возраст одним числом.")


@router.message(ProfileSG.bio, F.text)
async def profile_bio_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    bio = (message.text or "").strip()
    if len(bio) < 10:
        await message.answer("Минимум 10 символов — чуть подробнее.")
        return
    if len(bio) > 2000:
        bio = bio[:2000]

    data = await state.get_data()

    if data.get("edit_single") == "bio":
        user = await upsert_user_from_message(session, message)
        from sqlalchemy import update as sa_update
        from bot.models import User
        await session.execute(
            sa_update(User).where(User.id == user.id).values(bio=bio),
        )
        await state.clear()
        await message.answer("Текст «о себе» обновлён.", reply_markup=main_menu_reply())
        return

    avatar = data.get("avatar_file_id")
    age = data.get("age")
    if not avatar or age is None:
        await state.clear()
        await message.answer(
            "Данные анкеты потерялись. Начни снова.",
            reply_markup=main_menu_reply(),
        )
        return

    user = await upsert_user_from_message(session, message)
    await update_user_profile(
        session,
        user_id=user.id,
        avatar_file_id=str(avatar),
        age=int(age),
        bio=bio,
    )

    pending = data.get(PENDING_ACTIVITY_KEY)
    editing = data.get("editing", False)
    await state.clear()

    if editing:
        await message.answer("Профиль обновлён.", reply_markup=main_menu_reply())
        return

    text = "Готово — профиль сохранён. Дальше запись в один клик."

    # Авто-вступление в активность, на которую кликали до анкеты.
    if pending is not None:
        try:
            aid = int(pending)
        except (TypeError, ValueError):
            aid = None
        if aid is not None:
            activity = await get_activity(session, aid)
            if activity is not None and activity.status == ACTIVITY_PUBLISHED:
                _, action = await join_activity(
                    session, activity=activity, user_id=user.id,
                )
                if action == "created_joined":
                    if activity.kind == ACTIVITY_EVENT:
                        text += f"\n\n✅ Ты в списке участников «{esc(activity.title)}»."
                    else:
                        text += f"\n\n✅ Отклик на заявку «{esc(activity.title)}» отправлен автору."
                elif action == "created_pending":
                    text += (
                        f"\n\n⏳ Заявка на «{esc(activity.title)}» отправлена. "
                        "Ждём подтверждения организатора."
                    )
                else:  # already
                    text += "\n\nТы уже в списке — всё ок."
            else:
                text += "\n\nЭто уже недоступно — выбери другое."

    await message.answer(text, reply_markup=main_menu_reply())
