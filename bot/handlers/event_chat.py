"""Управление ссылкой на чат для своих событий и заявок.

UI живёт «рядом с профилем»: пользователь нажимает кнопку «💬 Чат» на
карточке своего события (или заявки) в профиле, и бот присылает отдельное
сообщение с текущим состоянием + возможностью добавить / изменить / удалить.

FSM `EditChatSG` — одно текстовое состояние, target хранится в state data.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
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

from bot.services.chat_invite_notify import (
    broadcast_event_chat_invite,
    broadcast_seeking_chat_invite,
)
from bot.services.company_seeking import get_seeking, update_seeking_chat_url
from bot.services.events import get_event, update_event_chat_url
from bot.services.users import upsert_telegram_user
from bot.utils.chat_link import InvalidChatLinkError, normalize_chat_link
from bot.utils.formatting import esc

router = Router(name="event_chat")


class EditChatSG(StatesGroup):
    waiting_link = State()


# Namespaces:
#   evch:show:<id>          — показать текущую ссылку для события
#   evch:add:<id>            — войти в FSM ввода
#   evch:edit:<id>           — войти в FSM (существующая ссылка)
#   evch:askdel:<id>         — спросить подтверждение удаления
#   evch:del:<id>            — удалить
#   evch:cancel              — отменить diaalog
# Аналогично с префиксом `skch:` для заявок.

EVCH = "evch"
SKCH = "skch"


# ──────────────────────────── helpers ────────────────────────────────────────


def _status_text(*, kind: str, title: str, chat_url: str | None) -> str:
    entity = "события" if kind == "event" else "заявки"
    header = f"<b>💬 Чат {entity} «{esc(title)}»</b>"
    if chat_url:
        return (
            f"{header}\n\n"
            f"Текущая ссылка:\n<code>{esc(chat_url)}</code>"
        )
    return (
        f"{header}\n\n"
        "Ссылка ещё не добавлена. Добавь, чтобы участники могли "
        "попасть в обсуждение."
    )


def _status_keyboard(*, kind: str, entity_id: int, has_url: bool) -> InlineKeyboardMarkup:
    prefix = EVCH if kind == "event" else SKCH
    if has_url:
        rows = [
            [
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"{prefix}:edit:{entity_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"{prefix}:askdel:{entity_id}"),
            ],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="➕ Добавить ссылку", callback_data=f"{prefix}:add:{entity_id}")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_delete_keyboard(*, kind: str, entity_id: int) -> InlineKeyboardMarkup:
    prefix = EVCH if kind == "event" else SKCH
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"{prefix}:del:{entity_id}"),
                InlineKeyboardButton(text="↩️ Отмена", callback_data=f"{prefix}:show:{entity_id}"),
            ],
        ],
    )


async def _load_event_for_owner(
    session: AsyncSession,
    *,
    event_id: int,
    organizer_id: int,
):
    event = await get_event(session, event_id)
    if event is None or event.organizer_id != organizer_id:
        return None
    return event


async def _load_seeking_for_owner(
    session: AsyncSession,
    *,
    seeking_id: int,
    author_id: int,
):
    seeking = await get_seeking(session, seeking_id)
    if seeking is None or seeking.author_id != author_id:
        return None
    return seeking


def _parse_id(data: str, *, prefix_parts: int) -> int | None:
    try:
        return int(data.split(":", prefix_parts)[prefix_parts])
    except (IndexError, ValueError):
        return None


# ──────────────────────────── EVENTS: show / add / edit / delete ─────────────


@router.callback_query(F.data.startswith(f"{EVCH}:show:"))
async def on_event_chat_show(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    event_id = _parse_id(callback.data, prefix_parts=2)
    if event_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    event = await _load_event_for_owner(session, event_id=event_id, organizer_id=user.id)
    if event is None:
        await callback.answer("Событие не найдено или это не твоё событие.", show_alert=True)
        return
    text = _status_text(kind="event", title=event.title, chat_url=event.chat_url)
    kb = _status_keyboard(kind="event", entity_id=event_id, has_url=bool(event.chat_url))
    # Редактируем предыдущее сообщение, если это тот же dialog.
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^evch:(add|edit):\d+$"))
async def on_event_chat_enter_fsm(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    event_id = _parse_id(callback.data, prefix_parts=2)
    if event_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    event = await _load_event_for_owner(session, event_id=event_id, organizer_id=user.id)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return
    await state.set_state(EditChatSG.waiting_link)
    await state.update_data(target_kind="event", target_id=event_id)
    await callback.message.answer(
        f"Пришли ссылку на чат события «{esc(event.title)}» "
        f"(например, <code>https://t.me/...</code>).\n"
        f"Отмена: /cancel",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{EVCH}:askdel:"))
async def on_event_chat_ask_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    event_id = _parse_id(callback.data, prefix_parts=2)
    if event_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    event = await _load_event_for_owner(session, event_id=event_id, organizer_id=user.id)
    if event is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return
    text = (
        f"<b>Удалить ссылку на чат</b> события «{esc(event.title)}»?\n"
        "Участники не получат уведомление о снятии."
    )
    kb = _confirm_delete_keyboard(kind="event", entity_id=event_id)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith(f"{EVCH}:del:"))
async def on_event_chat_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    event_id = _parse_id(callback.data, prefix_parts=2)
    if event_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ok, _, _ = await update_event_chat_url(
        session, event_id=event_id, organizer_id=user.id, new_url=None,
    )
    if not ok:
        await callback.answer("Не удалось удалить — это не твоё событие.", show_alert=True)
        return
    event = await get_event(session, event_id)
    title = event.title if event else "—"
    text = _status_text(kind="event", title=title, chat_url=None)
    kb = _status_keyboard(kind="event", entity_id=event_id, has_url=False)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer("Ссылка удалена")


# ──────────────────────────── SEEKINGS: show / add / edit / delete ───────────


@router.callback_query(F.data.startswith(f"{SKCH}:show:"))
async def on_seeking_chat_show(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    seeking_id = _parse_id(callback.data, prefix_parts=2)
    if seeking_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    seeking = await _load_seeking_for_owner(
        session, seeking_id=seeking_id, author_id=user.id,
    )
    if seeking is None:
        await callback.answer("Заявка не найдена или это не твоя заявка.", show_alert=True)
        return
    text = _status_text(kind="seeking", title=seeking.title, chat_url=seeking.chat_url)
    kb = _status_keyboard(kind="seeking", entity_id=seeking_id, has_url=bool(seeking.chat_url))
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^skch:(add|edit):\d+$"))
async def on_seeking_chat_enter_fsm(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    seeking_id = _parse_id(callback.data, prefix_parts=2)
    if seeking_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    seeking = await _load_seeking_for_owner(
        session, seeking_id=seeking_id, author_id=user.id,
    )
    if seeking is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    await state.set_state(EditChatSG.waiting_link)
    await state.update_data(target_kind="seeking", target_id=seeking_id)
    await callback.message.answer(
        f"Пришли ссылку на чат заявки «{esc(seeking.title)}» "
        f"(например, <code>https://t.me/...</code>).\n"
        f"Отмена: /cancel",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SKCH}:askdel:"))
async def on_seeking_chat_ask_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    seeking_id = _parse_id(callback.data, prefix_parts=2)
    if seeking_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    seeking = await _load_seeking_for_owner(
        session, seeking_id=seeking_id, author_id=user.id,
    )
    if seeking is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    text = (
        f"<b>Удалить ссылку на чат</b> заявки «{esc(seeking.title)}»?\n"
        "Откликнувшиеся не получат уведомление о снятии."
    )
    kb = _confirm_delete_keyboard(kind="seeking", entity_id=seeking_id)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith(f"{SKCH}:del:"))
async def on_seeking_chat_delete(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    seeking_id = _parse_id(callback.data, prefix_parts=2)
    if seeking_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ok, _, _ = await update_seeking_chat_url(
        session, seeking_id=seeking_id, author_id=user.id, new_url=None,
    )
    if not ok:
        await callback.answer("Не удалось удалить — это не твоя заявка.", show_alert=True)
        return
    seeking = await get_seeking(session, seeking_id)
    title = seeking.title if seeking else "—"
    text = _status_text(kind="seeking", title=title, chat_url=None)
    kb = _status_keyboard(kind="seeking", entity_id=seeking_id, has_url=False)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer("Ссылка удалена")


# ──────────────────────────── FSM: принимаем новый URL / /cancel ─────────────


@router.message(Command("cancel"), StateFilter(EditChatSG))
async def edit_chat_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, оставил как было.")


@router.message(EditChatSG.waiting_link, F.text)
async def edit_chat_link_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return
    try:
        link = normalize_chat_link(message.text or "")
    except InvalidChatLinkError as e:
        await message.answer(str(e), parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    kind = data.get("target_kind")
    target_id = data.get("target_id")
    if kind not in ("event", "seeking") or not isinstance(target_id, int):
        await state.clear()
        await message.answer("Сессия сбросилась — открой «💬 Чат» заново в профиле.")
        return

    user = await upsert_telegram_user(session, message.from_user)

    if kind == "event":
        ok, old_url, _ = await update_event_chat_url(
            session, event_id=target_id, organizer_id=user.id, new_url=link,
        )
        if not ok:
            await state.clear()
            await message.answer("Это не твоё событие — изменить нельзя.")
            return
        # Рассылка, только если раньше ссылки не было (первое заполнение).
        sent = 0
        if not old_url:
            event = await get_event(session, target_id)
            if event is not None:
                sent = await broadcast_event_chat_invite(session, bot, event=event)
        await state.clear()
        await message.answer(
            "Ссылка сохранена."
            + (f"\nОтправил приглашение {sent} участникам." if sent else ""),
        )
        return

    # seeking
    ok, old_url, _ = await update_seeking_chat_url(
        session, seeking_id=target_id, author_id=user.id, new_url=link,
    )
    if not ok:
        await state.clear()
        await message.answer("Это не твоя заявка — изменить нельзя.")
        return
    sent = 0
    if not old_url:
        seeking = await get_seeking(session, target_id)
        if seeking is not None:
            sent = await broadcast_seeking_chat_invite(session, bot, seeking=seeking)
    await state.clear()
    await message.answer(
        "Ссылка сохранена."
        + (f"\nОтправил приглашение {sent} откликнувшимся." if sent else ""),
    )
