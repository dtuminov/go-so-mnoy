"""Фильтры лент по тегам (события и «ищу компанию»).

Пикер открывается из ленты по кнопке «🔎 Фильтры». Временный выбор пользователя
хранится в FSM data под отдельными ключами, которые не пересекаются с FSM
создания события / заявки / анкеты — поэтому пикер не переводит пользователя
в собственный State и не ломает чужие flow.

Сохраняем финальный выбор в `users.search_prefs` (JSONB) — он живёт между
рестартами и между FSM-переключениями.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.company_seeking import build_feed_view as build_seeking_feed_view
from bot.keyboards.tag_picker import tag_picker_keyboard
from bot.services.event_feed import build_event_feed_view
from bot.services.search_prefs import (
    get_event_tag_filter,
    get_seeking_tag_filter,
    set_event_tag_filter,
    set_seeking_tag_filter,
)
from bot.services.tags import list_active_tags
from bot.services.users import upsert_telegram_user

router = Router(name="filters")


# Ключи временного выбора в FSM data — не пересекаются с create_event / profile / seeking.
TMP_EVENT_KEY = "filter_tmp_event_tag_ids"
TMP_SEEKING_KEY = "filter_tmp_seeking_tag_ids"


# ──────────────────────────── helpers ────────────────────────────────────────


async def _tmp_ids(state: FSMContext, key: str) -> set[int]:
    data = await state.get_data()
    return set(data.get(key, []) or [])


async def _save_tmp_ids(state: FSMContext, key: str, ids: set[int]) -> None:
    await state.update_data({key: sorted(ids)})


async def _render_picker(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    prefix: str,
    selected_ids: set[int],
    title: str,
) -> None:
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
        f"<b>{title}</b>\n"
        "Выбери один или несколько тегов. "
        "Нажми ✅ Применить, чтобы обновить ленту."
    )
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML,
            )
        except Exception:
            # Исходное сообщение могло быть с фото/без edit_text — шлём новое.
            await callback.message.answer(
                text, reply_markup=kb, parse_mode=ParseMode.HTML,
            )


# ──────────────────────────── EVENTS: open / toggle / apply / clear ──────────


@router.callback_query(F.data == "tp:e:open")
async def on_events_filter_open(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    # Стартуем временный выбор из уже сохранённого в БД фильтра.
    current = set(get_event_tag_filter(user))
    await _save_tmp_ids(state, TMP_EVENT_KEY, current)
    await _render_picker(
        callback,
        session,
        prefix="tp:e",
        selected_ids=current,
        title="🔎 Фильтр ленты событий",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tp:e:t:"))
async def on_events_filter_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
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
        tags=tags,
        selected_ids=current,
        prefix="tp:e",
        with_apply=True,
        with_clear=True,
        with_cancel=True,
    )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "tp:e:clear")
async def on_events_filter_clear(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await _save_tmp_ids(state, TMP_EVENT_KEY, set())
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=set(),
        prefix="tp:e",
        with_apply=True,
        with_clear=True,
        with_cancel=True,
    )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Выбор сброшен")


@router.callback_query(F.data == "tp:e:apply")
async def on_events_filter_apply(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = sorted(await _tmp_ids(state, TMP_EVENT_KEY))
    await set_event_tag_filter(session, user=user, tag_ids=ids)
    await state.update_data({TMP_EVENT_KEY: None})

    view = await build_event_feed_view(
        session,
        index=0,
        tag_ids=ids or None,
    )
    if view is None:
        await callback.message.edit_text(
            "По выбранным тегам нет событий. "
            "Сбрось фильтр и попробуй снова.",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return
    text, kb = view
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer("Фильтр применён")


@router.callback_query(F.data == "tp:e:cancel")
async def on_events_filter_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    await state.update_data({TMP_EVENT_KEY: None})
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_event_tag_filter(user)
    view = await build_event_feed_view(session, index=0, tag_ids=ids or None)
    if view is None:
        await callback.message.edit_text(
            "Сейчас событий нет. Загляни позже.",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return
    text, kb = view
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


# ──────────────────────────── SEEKINGS: open / toggle / apply / clear ────────


@router.callback_query(F.data == "tp:s:open")
async def on_seekings_filter_open(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    current = set(get_seeking_tag_filter(user))
    await _save_tmp_ids(state, TMP_SEEKING_KEY, current)
    await _render_picker(
        callback,
        session,
        prefix="tp:s",
        selected_ids=current,
        title="🔎 Фильтр заявок «ищу компанию»",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tp:s:t:"))
async def on_seekings_filter_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
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
        tags=tags,
        selected_ids=current,
        prefix="tp:s",
        with_apply=True,
        with_clear=True,
        with_cancel=True,
    )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "tp:s:clear")
async def on_seekings_filter_clear(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await _save_tmp_ids(state, TMP_SEEKING_KEY, set())
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=set(),
        prefix="tp:s",
        with_apply=True,
        with_clear=True,
        with_cancel=True,
    )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Выбор сброшен")


@router.callback_query(F.data == "tp:s:apply")
async def on_seekings_filter_apply(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = sorted(await _tmp_ids(state, TMP_SEEKING_KEY))
    await set_seeking_tag_filter(session, user=user, tag_ids=ids)
    await state.update_data({TMP_SEEKING_KEY: None})

    view = await build_seeking_feed_view(session, 0, tag_ids=ids or None)
    if view is None:
        await callback.message.edit_text(
            "По выбранным тегам нет активных заявок. "
            "Сбрось фильтр и попробуй снова.",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return
    text, kb = view
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer("Фильтр применён")


@router.callback_query(F.data == "tp:s:cancel")
async def on_seekings_filter_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    await state.update_data({TMP_SEEKING_KEY: None})
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_seeking_tag_filter(user)
    view = await build_seeking_feed_view(session, 0, tag_ids=ids or None)
    if view is None:
        await callback.message.edit_text(
            "Сейчас заявок нет. Загляни позже.",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer()
        return
    text, kb = view
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()
