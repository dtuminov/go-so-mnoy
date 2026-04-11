"""Навигация внутри профиля: хаб → секция → детали активности.

Всё живёт в одном фото-сообщении (caption), управление — через
`edit_caption`. Callback-префикс `prf:*` используется только здесь и
не пересекается с действиями над активностями (`al:`, `acan:`, …) —
те остаются в `handlers/activity.py` и после успеха вызывают
`rerender_profile_to_hub` (возврат на обзор).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.profile_view import (
    SECTION_CREATED,
    SECTION_INCOMING_PENDING,
    SECTION_OUTGOING_PENDING,
    SECTION_PARTICIPATING,
    build_activity_detail_view,
    build_hub_view,
    build_section_view,
)
from bot.services.users import upsert_telegram_user

router = Router(name="profile_nav")


_KNOWN_SECTIONS = {
    SECTION_PARTICIPATING,
    SECTION_CREATED,
    SECTION_INCOMING_PENDING,
    SECTION_OUTGOING_PENDING,
}


async def _edit_caption_or_text(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    """Единая точка перерисовки профиль-сообщения: если исходно это
    фото — правим caption, иначе text. Глотаем ошибки Telegram."""
    if callback.message is None:
        return
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        # message is not modified / устаревшее / и т. п.
        pass


# ──────────────────────────── hub ────────────────────────────────────────────


@router.callback_query(F.data == "prf:hub")
async def on_profile_hub(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    text, kb = await build_hub_view(session, user)
    await _edit_caption_or_text(callback, text=text, reply_markup=kb)
    await callback.answer()


# ──────────────────────────── section list ──────────────────────────────────


@router.callback_query(F.data.startswith("prf:sec:"))
async def on_profile_section(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        section = callback.data.split(":", 2)[2]
    except IndexError:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    if section not in _KNOWN_SECTIONS:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    text, kb = await build_section_view(session, user, section=section)
    await _edit_caption_or_text(callback, text=text, reply_markup=kb)
    await callback.answer()


# ──────────────────────────── activity detail ───────────────────────────────


@router.callback_query(F.data.startswith("prf:act:"))
async def on_profile_activity(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    # Формат: prf:act:<section>:<id>
    parts = callback.data.split(":", 3)
    if len(parts) < 4:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    section = parts[2]
    try:
        activity_id = int(parts[3])
    except ValueError:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    if section not in _KNOWN_SECTIONS:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    view = await build_activity_detail_view(
        session,
        user,
        activity_id=activity_id,
        from_section=section,
    )
    if view is None:
        await callback.answer("Активность не найдена", show_alert=True)
        # Откатываемся к списку — там она тоже пропадёт.
        text, kb = await build_section_view(session, user, section=section)
        await _edit_caption_or_text(callback, text=text, reply_markup=kb)
        return
    text, kb = view
    await _edit_caption_or_text(callback, text=text, reply_markup=kb)
    await callback.answer()
