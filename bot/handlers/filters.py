"""Фильтры лент по тегам.

Поскольку у нас визуально две ленты — «Найти событие» (kind='event') и
«Найти компанию» (kind='seeking') — фильтры тоже разделены на два набора:
`tp:e:*` / `tp:s:*`. Соответствие kind ↔ namespace инкапсулировано в
константах ниже.

Пикер не переводит пользователя в собственный State — временный выбор
живёт в FSM data под отдельными ключами, не пересекающимися с FSM
создания / анкеты / редактирования чата.

Финальный выбор сохраняется в `users.search_prefs` (JSONB) — переживает
рестарты и сброс FSM.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, ACTIVITY_SEEKING
from bot.keyboards.tag_picker import tag_picker_keyboard
from bot.services.activity_feed import build_activity_feed_view
from bot.keyboards.main_menu import MENU_BUTTONS
from bot.services.cities import search_cities
from bot.services.cover import edit_to_activity_cover
from bot.services.search_prefs import (
    get_event_tag_filter,
    get_filter_city_id,
    get_seeking_tag_filter,
    set_event_tag_filter,
    set_filter_city,
    set_seeking_tag_filter,
)
from bot.services.tags import list_active_tags
from bot.services.users import upsert_telegram_user

router = Router(name="filters")


TMP_EVENT_KEY = "filter_tmp_event_tag_ids"
TMP_SEEKING_KEY = "filter_tmp_seeking_tag_ids"
TMP_FILTER_CITY_KEY = "filter_tmp_city_id"


class FilterCitySG(StatesGroup):
    waiting_city = State()


# ──────────────────────────── helpers ────────────────────────────────────────


async def _tmp_ids(state: FSMContext, key: str) -> set[int]:
    data = await state.get_data()
    return set(data.get(key, []) or [])


async def _save_tmp_ids(state: FSMContext, key: str, ids: set[int]) -> None:
    await state.update_data({key: sorted(ids)})


async def _safe_edit_markup(callback: CallbackQuery, kb) -> None:
    """edit_reply_markup, который не падает на «message is not modified».

    Telegram возвращает 400, если новая клавиатура байт-в-байт совпадает
    со старой (например, кнопка «🗑 Сбросить» внутри пикера, когда уже
    ничего не выбрано). Молча проглатываем — для пользователя ничего
    не меняется, и это лучше, чем тащить ошибку наружу.
    """
    if callback.message is None:
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


async def _render_filter_menu(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    prefix: str,
    city_name: str = "",
) -> None:
    """Меню фильтров: две кнопки — город и теги."""
    city_label = f"📍 {city_name}" if city_name else "📍 Город"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=city_label, callback_data=f"{prefix}:city:change"),
            InlineKeyboardButton(text="🏷 Теги", callback_data=f"{prefix}:tags"),
        ],
        [InlineKeyboardButton(text="✖️ Закрыть", callback_data=f"{prefix}:cancel")],
    ])
    text = "<b>🔎 Фильтры</b>\nВыбери что настроить:"
    if callback.message is None:
        return
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, reply_markup=kb, parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.edit_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML,
            )
    except Exception:
        pass


async def _render_tag_picker(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    prefix: str,
    selected_ids: set[int],
) -> None:
    """Пикер тегов (второй уровень)."""
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=selected_ids,
        prefix=prefix,
        with_apply=True,
        with_clear=True,
        with_cancel=True,
    )
    text = (
        "<b>🏷 Фильтр по тегам</b>\n"
        "Выбери теги и нажми ✅ Применить."
    )
    if callback.message is None:
        return
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, reply_markup=kb, parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.edit_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML,
            )
    except Exception:
        pass


def _empty_state_reset_kb(kind: str, *, has_city_filter: bool = False) -> InlineKeyboardMarkup:
    """Inline-кнопки сброса для empty-state ленты."""
    reset_cb = "tp:e:reset" if kind == ACTIVITY_EVENT else "tp:s:reset"
    rows = [
        [InlineKeyboardButton(text="🗑 Сбросить фильтры", callback_data=reset_cb)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_feed_after(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    user,
    kind: str,
    tag_ids: list[int],
    empty_hint: str,
) -> None:
    if callback.message is None:
        return
    filter_city_id = get_filter_city_id(user)
    city_id = filter_city_id if filter_city_id is not None else user.city_id
    from bot.models import City
    city = await session.get(City, city_id)
    city_name = city.name if city else ""
    view = await build_activity_feed_view(
        session,
        kind=kind,
        index=0,
        city_id=city_id,
        city_name=city_name,
        tag_ids=tag_ids or None,
        viewer_user_id=user.id,
    )
    if view is None:
        has_any_filter = bool(tag_ids) or filter_city_id is not None
        empty_kb = _empty_state_reset_kb(kind) if has_any_filter else None
        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=empty_hint,
                    reply_markup=empty_kb,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await callback.message.edit_text(
                    empty_hint,
                    reply_markup=empty_kb,
                    parse_mode=ParseMode.HTML,
                )
        except Exception:
            pass
        return

    cover_file_id, text, kb = view
    await edit_to_activity_cover(
        callback.message,
        cover_file_id=cover_file_id,
        caption=text,
        reply_markup=kb,
    )


# ──────────────────────────── EVENTS feed: tp:e:* ────────────────────────────


async def _get_filter_city_name(session: AsyncSession, user) -> str:
    """Возвращает имя города для фильтра (из search_prefs или профиля)."""
    filter_city_id = get_filter_city_id(user)
    city_id = filter_city_id if filter_city_id is not None else user.city_id
    from bot.models import City
    city = await session.get(City, city_id)
    return city.name if city else ""


@router.callback_query(F.data == "tp:e:open")
async def on_events_filter_open(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    city_name = await _get_filter_city_name(session, user)
    await _render_filter_menu(callback, session, prefix="tp:e", city_name=city_name)
    await callback.answer()


@router.callback_query(F.data == "tp:e:tags")
async def on_events_tags_open(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    current = set(get_event_tag_filter(user))
    await _save_tmp_ids(state, TMP_EVENT_KEY, current)
    await _render_tag_picker(callback, session, prefix="tp:e", selected_ids=current)
    await callback.answer()


@router.callback_query(F.data.startswith("tp:e:t:"))
async def on_events_filter_toggle(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    try:
        tag_id = int(callback.data.split(":", 3)[3])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    current = await _tmp_ids(state, TMP_EVENT_KEY)
    if tag_id in current:
        current.remove(tag_id)
    else:
        current.add(tag_id)
    await _save_tmp_ids(state, TMP_EVENT_KEY, current)
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags, selected_ids=current, prefix="tp:e",
        with_apply=True, with_clear=True, with_cancel=True,
    )
    await _safe_edit_markup(callback, kb)
    await callback.answer()


@router.callback_query(F.data == "tp:e:clear")
async def on_events_filter_clear(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    await _save_tmp_ids(state, TMP_EVENT_KEY, set())
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags, selected_ids=set(), prefix="tp:e",
        with_apply=True, with_clear=True, with_cancel=True,
    )
    await _safe_edit_markup(callback, kb)
    await callback.answer("Выбор сброшен")


@router.callback_query(F.data == "tp:e:apply")
async def on_events_filter_apply(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = sorted(await _tmp_ids(state, TMP_EVENT_KEY))
    await set_event_tag_filter(session, user=user, tag_ids=ids)
    await state.update_data({TMP_EVENT_KEY: None})
    await _render_feed_after(
        callback, session, user=user, kind=ACTIVITY_EVENT, tag_ids=ids,
        empty_hint="По выбранным тегам нет событий. Сбрось фильтр и попробуй снова.",
    )
    await callback.answer("Фильтр применён")


@router.callback_query(F.data == "tp:e:cancel")
async def on_events_filter_cancel(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    await state.update_data({TMP_EVENT_KEY: None})
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_event_tag_filter(user)
    await _render_feed_after(
        callback, session, user=user, kind=ACTIVITY_EVENT, tag_ids=ids,
        empty_hint="Сейчас событий нет. Загляни позже.",
    )
    await callback.answer()


@router.callback_query(F.data == "tp:e:reset")
async def on_events_filter_reset(
    callback: CallbackQuery, session: AsyncSession,
) -> None:
    """Сброс всех фильтров событий (теги + город)."""
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    await set_event_tag_filter(session, user=user, tag_ids=[])
    await set_filter_city(session, user=user, city_id=None)
    await _render_feed_after(
        callback, session, user=user, kind=ACTIVITY_EVENT, tag_ids=[],
        empty_hint="Сейчас событий нет. Загляни позже.",
    )
    await callback.answer("Фильтры сброшены")


# ──────────────────────────── SEEKINGS feed: tp:s:* ──────────────────────────


@router.callback_query(F.data == "tp:s:open")
async def on_seekings_filter_open(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    city_name = await _get_filter_city_name(session, user)
    await _render_filter_menu(callback, session, prefix="tp:s", city_name=city_name)
    await callback.answer()


@router.callback_query(F.data == "tp:s:tags")
async def on_seekings_tags_open(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    current = set(get_seeking_tag_filter(user))
    await _save_tmp_ids(state, TMP_SEEKING_KEY, current)
    await _render_tag_picker(callback, session, prefix="tp:s", selected_ids=current)
    await callback.answer()


@router.callback_query(F.data.startswith("tp:s:t:"))
async def on_seekings_filter_toggle(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    try:
        tag_id = int(callback.data.split(":", 3)[3])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    current = await _tmp_ids(state, TMP_SEEKING_KEY)
    if tag_id in current:
        current.remove(tag_id)
    else:
        current.add(tag_id)
    await _save_tmp_ids(state, TMP_SEEKING_KEY, current)
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags, selected_ids=current, prefix="tp:s",
        with_apply=True, with_clear=True, with_cancel=True,
    )
    await _safe_edit_markup(callback, kb)
    await callback.answer()


@router.callback_query(F.data == "tp:s:clear")
async def on_seekings_filter_clear(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    await _save_tmp_ids(state, TMP_SEEKING_KEY, set())
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags, selected_ids=set(), prefix="tp:s",
        with_apply=True, with_clear=True, with_cancel=True,
    )
    await _safe_edit_markup(callback, kb)
    await callback.answer("Выбор сброшен")


@router.callback_query(F.data == "tp:s:apply")
async def on_seekings_filter_apply(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = sorted(await _tmp_ids(state, TMP_SEEKING_KEY))
    await set_seeking_tag_filter(session, user=user, tag_ids=ids)
    await state.update_data({TMP_SEEKING_KEY: None})
    await _render_feed_after(
        callback, session, user=user, kind=ACTIVITY_SEEKING, tag_ids=ids,
        empty_hint="По выбранным тегам нет активных заявок. Сбрось фильтр и попробуй снова.",
    )
    await callback.answer("Фильтр применён")


@router.callback_query(F.data == "tp:s:cancel")
async def on_seekings_filter_cancel(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    await state.update_data({TMP_SEEKING_KEY: None})
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_seeking_tag_filter(user)
    await _render_feed_after(
        callback, session, user=user, kind=ACTIVITY_SEEKING, tag_ids=ids,
        empty_hint="Сейчас заявок нет. Загляни позже.",
    )
    await callback.answer()


@router.callback_query(F.data == "tp:s:reset")
async def on_seekings_filter_reset(
    callback: CallbackQuery, session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    await set_seeking_tag_filter(session, user=user, tag_ids=[])
    await set_filter_city(session, user=user, city_id=None)
    await _render_feed_after(
        callback, session, user=user, kind=ACTIVITY_SEEKING, tag_ids=[],
        empty_hint="Сейчас заявок нет. Загляни позже.",
    )
    await callback.answer("Фильтры сброшены")


# ──────────────────────────── city in filter picker ────────────────────────────


@router.callback_query(F.data.regexp(r"^tp:[es]:city:change$"), StateFilter(default_state))
async def on_filter_city_change(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    prefix = callback.data[:4]  # "tp:e" or "tp:s"
    await state.update_data(filter_city_prefix=prefix)
    await state.set_state(FilterCitySG.waiting_city)
    await callback.answer()
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await callback.message.answer(
        "Отправь геолокацию или напиши название города:",
        reply_markup=kb,
    )


@router.message(FilterCitySG.waiting_city, F.location)
async def on_filter_city_location(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    """Юзер отправил геолокацию для смены города в фильтре."""
    from aiogram.types import ReplyKeyboardRemove
    from bot.utils.geo import city_name_by_coords

    lat = message.location.latitude
    lon = message.location.longitude
    city_name = await city_name_by_coords(lat, lon)
    if not city_name:
        await message.answer(
            "Не удалось определить город. Напиши название текстом.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    cities = await search_cities(session, city_name, limit=1)
    if not cities:
        await message.answer(
            f"Город «{city_name}» не найден в базе. Попробуй написать название.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    city = cities[0]
    user = await upsert_telegram_user(session, message.from_user)
    await set_filter_city(session, user=user, city_id=city.id)

    data = await state.get_data()
    prefix = data.get("filter_city_prefix", "tp:e")
    await state.set_state(default_state)

    if prefix == "tp:e":
        kind = ACTIVITY_EVENT
        tag_ids = get_event_tag_filter(user)
    else:
        kind = ACTIVITY_SEEKING
        tag_ids = get_seeking_tag_filter(user)

    from bot.keyboards.main_menu import main_menu_reply
    btn = "📍 Найти событие" if kind == ACTIVITY_EVENT else "🤝 Найти компанию"
    await message.answer(
        f"Город фильтра: {city.name} ✓\nНажми «{btn}» чтобы обновить ленту.",
        reply_markup=main_menu_reply(),
    )


@router.message(FilterCitySG.waiting_city, F.text, ~F.text.in_(MENU_BUTTONS))
async def on_filter_city_search(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    query = (message.text or "").strip()
    if len(query) < 2:
        await message.answer("Напиши хотя бы 2 символа.")
        return
    cities = await search_cities(session, query)
    if not cities:
        await message.answer("Не нашёл такого города. Попробуй ещё раз.")
        return
    rows = [
        [InlineKeyboardButton(text=c.name, callback_data=f"fltcity:{c.id}")]
        for c in cities
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="fltcity:cancel")])
    await message.answer(
        "Выбери город:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "fltcity:cancel", StateFilter(FilterCitySG.waiting_city))
async def on_filter_city_cancel(
    callback: CallbackQuery, state: FSMContext,
) -> None:
    await state.set_state(default_state)
    await callback.answer("Отменено.")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("fltcity:"), StateFilter(FilterCitySG.waiting_city))
async def on_filter_city_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        city_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer()
        return

    user = await upsert_telegram_user(session, callback.from_user)
    await set_filter_city(session, user=user, city_id=city_id)

    data = await state.get_data()
    prefix = data.get("filter_city_prefix", "tp:e")
    await state.set_state(default_state)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    city_name = await _get_filter_city_name(session, user)

    # Определяем kind и tag_ids из prefix
    if prefix == "tp:e":
        kind = ACTIVITY_EVENT
        tag_ids = get_event_tag_filter(user)
    else:
        kind = ACTIVITY_SEEKING
        tag_ids = get_seeking_tag_filter(user)

    await _render_feed_after(
        callback, session, user=user, kind=kind,
        tag_ids=tag_ids,
        empty_hint="По текущим фильтрам ничего нет.",
    )
    await callback.answer(f"Город: {city_name}")
