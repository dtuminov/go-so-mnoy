"""Сборка карточки профиля пользователя (caption + inline-клавиатура).

Используется в `handlers/menu.py` (открытие профиля) и в хэндлерах
мутаций (отписка / отмена / закрытие / снятие отклика) — для перерисовки
карточки на месте.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, ACTIVITY_SEEKING
from bot.models import User
from bot.services.activities import (
    get_user_created_activities,
    get_user_joined_activities,
    get_user_pending_activities,
)
from bot.utils.formatting import esc, format_datetime_msk


async def build_profile_view(
    session: AsyncSession,
    user: User,
) -> tuple[str, InlineKeyboardMarkup]:
    """Возвращает `(caption, keyboard)` для карточки профиля."""
    name = esc(user.first_name or user.username or "Ты")
    lines = [f"<b>👤 {name}</b>", f"Возраст: {user.age}", "", esc(user.bio or "")]
    inline_rows: list[list[InlineKeyboardButton]] = []

    # ── Записан на события (joined) ─────────────────────────────────────────
    joined_events = await get_user_joined_activities(
        session, user_id=user.id, kind=ACTIVITY_EVENT,
    )
    if joined_events:
        lines += ["", "<b>Мои записи на события:</b>"]
        for ev in joined_events:
            lines.append(
                f"• {esc(ev.title)} — {format_datetime_msk(ev.starts_at)}"
            )
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"❌ Отписаться: {esc(ev.title[:30])}",
                    callback_data=f"al:{ev.id}",
                )
            ])
    else:
        lines += ["", "Пока не записан ни на одно событие."]

    # ── Pending-заявки (на private события) ─────────────────────────────────
    pending = await get_user_pending_activities(session, user_id=user.id)
    if pending:
        lines += ["", "<b>Жду подтверждения:</b>"]
        for act in pending:
            when = (
                f" — {format_datetime_msk(act.starts_at)}"
                if act.starts_at
                else ""
            )
            lines.append(f"⏳ {esc(act.title)}{when}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"↩️ Отозвать: {esc(act.title[:24])}",
                    callback_data=f"al:{act.id}",
                ),
            ])

    # ── Организованные события (creator, kind='event') ──────────────────────
    organized = await get_user_created_activities(
        session, user_id=user.id, kind=ACTIVITY_EVENT,
    )
    if organized:
        lines += ["", "<b>Мои события (организатор):</b>"]
        for ev in organized:
            status_icon = "✅" if ev.status == "published" else "🕐"
            chat_mark = " · 💬" if ev.chat_url else ""
            vis_mark = " · 🔒" if ev.visibility == "private" else ""
            lines.append(
                f"{status_icon} {esc(ev.title)}{chat_mark}{vis_mark} — "
                f"{format_datetime_msk(ev.starts_at)}"
            )
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"👥 Участники: {esc(ev.title[:20])}",
                    callback_data=f"amem:{ev.id}",
                ),
                InlineKeyboardButton(
                    text="🚫 Отменить",
                    callback_data=f"acan:{ev.id}",
                ),
            ])
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"💬 Чат: {esc(ev.title[:24])}",
                    callback_data=f"actch:show:{ev.id}",
                ),
                InlineKeyboardButton(
                    text=f"🔒 Доступ: {esc(ev.title[:18])}",
                    callback_data=f"avis:show:{ev.id}",
                ),
            ])

    # ── Мои отклики на чужие заявки (joined seeking) ────────────────────────
    joined_seekings = await get_user_joined_activities(
        session, user_id=user.id, kind=ACTIVITY_SEEKING,
    )
    if joined_seekings:
        lines += ["", "<b>Мои отклики:</b>"]
        for sk in joined_seekings:
            lines.append(f"• {esc(sk.title)}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"❌ Убрать отклик: {esc(sk.title[:24])}",
                    callback_data=f"al:{sk.id}",
                ),
            ])

    # ── Мои заявки «ищу компанию» (creator, kind='seeking') ─────────────────
    my_seekings = await get_user_created_activities(
        session, user_id=user.id, kind=ACTIVITY_SEEKING,
    )
    if my_seekings:
        lines += ["", "<b>Мои заявки:</b>"]
        for sk in my_seekings:
            status_icon = "✅" if sk.status == "published" else "🕐"
            chat_mark = " · 💬" if sk.chat_url else ""
            lines.append(f"{status_icon} {esc(sk.title)}{chat_mark}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"👥 Отклики: {esc(sk.title[:20])}",
                    callback_data=f"amem:{sk.id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Закрыть",
                    callback_data=f"aclose:{sk.id}",
                ),
            ])
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"💬 Чат: {esc(sk.title[:24])}",
                    callback_data=f"actch:show:{sk.id}",
                ),
            ])

    inline_rows.append([
        InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="profile:edit"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=inline_rows)


async def rerender_profile_card(
    callback_message,
    session: AsyncSession,
    user: User,
) -> None:
    """Перерисовывает карточку профиля на месте (caption или text)."""
    from aiogram.enums import ParseMode

    text, kb = await build_profile_view(session, user)
    try:
        if callback_message.photo:
            await callback_message.edit_caption(
                caption=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback_message.edit_text(
                text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        # Сообщение могло устареть/быть удалённым — молча пропускаем.
        pass
