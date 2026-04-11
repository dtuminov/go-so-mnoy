"""Управление настройками активности из профиля:

- chat_url: показать / добавить / изменить / удалить (`actch:*`),
  при первом заполнении — broadcast приглашений уже подтверждённым.
- visibility: показать / переключить (`avis:*`).
- cover: показать / заменить / сбросить (`actcv:*`).
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

from bot.constants import VISIBILITY_OPEN, VISIBILITY_PRIVATE
from bot.services.activities import (
    get_activity,
    update_chat_url,
    update_cover,
    update_visibility,
)
from bot.services.chat_invite_notify import broadcast_chat_invite
from bot.services.users import upsert_telegram_user
from bot.utils.chat_link import InvalidChatLinkError, normalize_chat_link
from bot.utils.formatting import esc

router = Router(name="activity_chat")


# ──────────────────────────── EditChatSG ─────────────────────────────────────


class EditChatSG(StatesGroup):
    waiting_link = State()


class EditCoverSG(StatesGroup):
    waiting_photo = State()


# ──────────────────────────── helpers ────────────────────────────────────────


async def _load_activity_for_creator(
    session: AsyncSession, *, activity_id: int, creator_id: int,
):
    activity = await get_activity(session, activity_id)
    if activity is None or activity.creator_id != creator_id:
        return None
    return activity


def _entity_word(kind: str) -> str:
    return "события" if kind == "event" else "заявки"


def _chat_status_text(*, kind: str, title: str, chat_url: str | None) -> str:
    header = f"<b>💬 Чат {_entity_word(kind)} «{esc(title)}»</b>"
    if chat_url:
        return f"{header}\n\nТекущая ссылка:\n<code>{esc(chat_url)}</code>"
    return (
        f"{header}\n\nСсылка ещё не добавлена. Добавь, чтобы участники "
        "могли попасть в обсуждение."
    )


def _chat_status_keyboard(activity_id: int, has_url: bool) -> InlineKeyboardMarkup:
    if has_url:
        rows = [
            [
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"actch:edit:{activity_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"actch:askdel:{activity_id}"),
            ],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="➕ Добавить ссылку", callback_data=f"actch:add:{activity_id}")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_delete_keyboard(activity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"actch:del:{activity_id}"),
                InlineKeyboardButton(text="↩️ Отмена", callback_data=f"actch:show:{activity_id}"),
            ],
        ],
    )


async def _edit_or_send(callback: CallbackQuery, *, text: str, kb: InlineKeyboardMarkup) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


def _parse_id(data: str, *, parts_before: int) -> int | None:
    try:
        return int(data.split(":", parts_before)[parts_before])
    except (IndexError, ValueError):
        return None


# ──────────────────────────── chat_url: show ─────────────────────────────────


@router.callback_query(F.data.startswith("actch:show:"))
async def on_chat_show(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    activity = await _load_activity_for_creator(
        session, activity_id=activity_id, creator_id=user.id,
    )
    if activity is None:
        await callback.answer("Не найдено или это не твоё.", show_alert=True)
        return
    text = _chat_status_text(
        kind=activity.kind, title=activity.title, chat_url=activity.chat_url,
    )
    kb = _chat_status_keyboard(activity_id, has_url=bool(activity.chat_url))
    await _edit_or_send(callback, text=text, kb=kb)
    await callback.answer()


# ──────────────────────────── chat_url: add / edit ───────────────────────────


@router.callback_query(F.data.regexp(r"^actch:(add|edit):\d+$"))
async def on_chat_enter_fsm(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    activity = await _load_activity_for_creator(
        session, activity_id=activity_id, creator_id=user.id,
    )
    if activity is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    await state.set_state(EditChatSG.waiting_link)
    await state.update_data(target_activity_id=activity_id)
    await callback.message.answer(
        f"Пришли ссылку на чат «{esc(activity.title)}» "
        f"(например, <code>https://t.me/...</code>).\nОтмена: /cancel",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


# ──────────────────────────── chat_url: delete ──────────────────────────────


@router.callback_query(F.data.startswith("actch:askdel:"))
async def on_chat_ask_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    activity = await _load_activity_for_creator(
        session, activity_id=activity_id, creator_id=user.id,
    )
    if activity is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    text = (
        f"<b>Удалить ссылку на чат</b> «{esc(activity.title)}»?\n"
        "Участники не получат уведомление о снятии."
    )
    kb = _confirm_delete_keyboard(activity_id)
    await _edit_or_send(callback, text=text, kb=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("actch:del:"))
async def on_chat_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ok, _, _ = await update_chat_url(
        session, activity_id=activity_id, actor_id=user.id, new_url=None,
    )
    if not ok:
        await callback.answer("Не удалось — это не твоё.", show_alert=True)
        return
    activity = await get_activity(session, activity_id)
    title = activity.title if activity else "—"
    kind = activity.kind if activity else "event"
    text = _chat_status_text(kind=kind, title=title, chat_url=None)
    kb = _chat_status_keyboard(activity_id, has_url=False)
    await _edit_or_send(callback, text=text, kb=kb)
    await callback.answer("Удалено")


# ──────────────────────────── EditChatSG: текстовый ввод ────────────────────


@router.message(Command("cancel"), StateFilter(EditChatSG))
async def edit_chat_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, оставил как было.")


@router.message(EditChatSG.waiting_link, F.text)
async def edit_chat_link_save(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot,
) -> None:
    if message.from_user is None:
        return
    try:
        link = normalize_chat_link(message.text or "")
    except InvalidChatLinkError as e:
        await message.answer(str(e), parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    activity_id = data.get("target_activity_id")
    if not isinstance(activity_id, int):
        await state.clear()
        await message.answer("Сессия сбросилась — открой «💬 Чат» заново в профиле.")
        return

    user = await upsert_telegram_user(session, message.from_user)
    ok, old_url, _ = await update_chat_url(
        session, activity_id=activity_id, actor_id=user.id, new_url=link,
    )
    if not ok:
        await state.clear()
        await message.answer("Это не твоё — изменить нельзя.")
        return

    sent = 0
    if not old_url:
        activity = await get_activity(session, activity_id)
        if activity is not None:
            sent = await broadcast_chat_invite(session, bot, activity=activity)

    await state.clear()
    extra = (
        f"\nОтправил приглашение {sent} участникам." if sent else ""
    )
    await message.answer("Ссылка сохранена." + extra)


# ──────────────────────────── visibility manager ────────────────────────────


def _vis_status_text(*, title: str, visibility: str) -> str:
    if visibility == VISIBILITY_PRIVATE:
        body = (
            "🔒 <b>Закрытое</b>: новые участники сначала попадают в "
            "«ожидание», организатор подтверждает каждого вручную."
        )
    else:
        body = (
            "🌐 <b>Открытое</b>: каждый, кто нажал «Иду», сразу в "
            "списке участников."
        )
    return f"<b>Доступ к «{esc(title)}»</b>\n\n{body}"


def _vis_keyboard(activity_id: int, current: str) -> InlineKeyboardMarkup:
    open_label = "🌐 Открытое" + (" ✓" if current == VISIBILITY_OPEN else "")
    private_label = "🔒 Закрытое" + (" ✓" if current == VISIBILITY_PRIVATE else "")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=open_label, callback_data=f"avis:set:{activity_id}:open"),
                InlineKeyboardButton(text=private_label, callback_data=f"avis:set:{activity_id}:private"),
            ],
        ],
    )


@router.callback_query(F.data.startswith("avis:show:"))
async def on_visibility_show(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    activity = await _load_activity_for_creator(
        session, activity_id=activity_id, creator_id=user.id,
    )
    if activity is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    text = _vis_status_text(title=activity.title, visibility=activity.visibility)
    kb = _vis_keyboard(activity_id, activity.visibility)
    await _edit_or_send(callback, text=text, kb=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("avis:set:"))
async def on_visibility_set(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        _, _, activity_id_raw, value = callback.data.split(":", 3)
        activity_id = int(activity_id_raw)
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    if value not in (VISIBILITY_OPEN, VISIBILITY_PRIVATE):
        await callback.answer("Некорректное значение", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ok = await update_visibility(
        session, activity_id=activity_id, actor_id=user.id, new_visibility=value,
    )
    if not ok:
        await callback.answer("Не удалось — это не твоё.", show_alert=True)
        return
    activity = await get_activity(session, activity_id)
    if activity is None:
        await callback.answer("Готово.")
        return
    text = _vis_status_text(title=activity.title, visibility=activity.visibility)
    kb = _vis_keyboard(activity_id, activity.visibility)
    await _edit_or_send(callback, text=text, kb=kb)
    await callback.answer("Готово")


# ──────────────────────────── cover manager ────────────────────────────────


def _cover_status_text(*, title: str, has_custom: bool) -> str:
    state = "своя картинка" if has_custom else "стандартная"
    return (
        f"<b>🖼 Обложка «{esc(title)}»</b>\n\n"
        f"Сейчас: <b>{state}</b>.\n\n"
        "Пришли новое фото, чтобы заменить (если активность уже была "
        "опубликована — обложка обновится для всех)."
    )


def _cover_keyboard(activity_id: int, has_custom: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            text="📷 Прислать новое фото",
            callback_data=f"actcv:edit:{activity_id}",
        )],
    ]
    if has_custom:
        rows.append([InlineKeyboardButton(
            text="🗑 Сбросить на стандартную",
            callback_data=f"actcv:reset:{activity_id}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("actcv:show:"))
async def on_cover_show(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    activity = await _load_activity_for_creator(
        session, activity_id=activity_id, creator_id=user.id,
    )
    if activity is None:
        await callback.answer("Не найдено или это не твоё.", show_alert=True)
        return
    text = _cover_status_text(
        title=activity.title, has_custom=bool(activity.cover_file_id),
    )
    kb = _cover_keyboard(activity_id, has_custom=bool(activity.cover_file_id))
    await _edit_or_send(callback, text=text, kb=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("actcv:edit:"))
async def on_cover_enter_fsm(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    activity = await _load_activity_for_creator(
        session, activity_id=activity_id, creator_id=user.id,
    )
    if activity is None:
        await callback.answer("Не найдено.", show_alert=True)
        return
    await state.set_state(EditCoverSG.waiting_photo)
    await state.update_data(target_activity_id=activity_id)
    await callback.message.answer(
        f"Пришли новое фото для обложки «{esc(activity.title)}». "
        "Отмена: /cancel",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("actcv:reset:"))
async def on_cover_reset(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    activity_id = _parse_id(callback.data, parts_before=2)
    if activity_id is None:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ok = await update_cover(
        session, activity_id=activity_id, actor_id=user.id, new_file_id=None,
    )
    if not ok:
        await callback.answer("Не удалось — это не твоё.", show_alert=True)
        return
    activity = await get_activity(session, activity_id)
    title = activity.title if activity else "—"
    text = _cover_status_text(title=title, has_custom=False)
    kb = _cover_keyboard(activity_id, has_custom=False)
    await _edit_or_send(callback, text=text, kb=kb)
    await callback.answer("Сброшено")


@router.message(Command("cancel"), StateFilter(EditCoverSG))
async def cover_edit_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, оставил как было.")


@router.message(EditCoverSG.waiting_photo, F.photo)
async def cover_edit_save(
    message: Message, state: FSMContext, session: AsyncSession,
) -> None:
    if message.from_user is None:
        return
    photos = message.photo or []
    if not photos:
        await message.answer("Пришли фото или /cancel.")
        return
    file_id = photos[-1].file_id

    data = await state.get_data()
    activity_id = data.get("target_activity_id")
    if not isinstance(activity_id, int):
        await state.clear()
        await message.answer(
            "Сессия сбросилась — открой «🖼 Обложка» заново в профиле.",
        )
        return

    user = await upsert_telegram_user(session, message.from_user)
    ok = await update_cover(
        session, activity_id=activity_id, actor_id=user.id, new_file_id=file_id,
    )
    if not ok:
        await state.clear()
        await message.answer("Это не твоё — изменить нельзя.")
        return
    await state.clear()
    await message.answer("Обложка обновлена ✅")


@router.message(EditCoverSG.waiting_photo)
async def cover_edit_wrong(message: Message) -> None:
    await message.answer("Жду <b>фото</b>. Или /cancel.", parse_mode=ParseMode.HTML)
