"""Сборка карточки профиля пользователя (caption + inline-клавиатура).

Вынесено в сервисный слой, чтобы хэндлеры мутаций (отписка от события,
отмена своего события, закрытие заявки, снятие отклика) могли перерисовать
профиль на месте через `edit_caption` / `edit_text`, не импортируя друг
друга и не создавая кругов между роутерами.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import User
from bot.services.company_seeking import (
    get_user_responded_seekings,
    get_user_seekings,
)
from bot.services.events import get_user_joined_events, get_user_organized_events
from bot.utils.formatting import esc, format_datetime_msk


async def build_profile_view(
    session: AsyncSession,
    user: User,
) -> tuple[str, InlineKeyboardMarkup]:
    """Возвращает `(caption, keyboard)` для карточки профиля."""
    name = esc(user.first_name or user.username or "Ты")
    lines = [f"<b>👤 {name}</b>", f"Возраст: {user.age}", "", esc(user.bio or "")]
    inline_rows: list[list[InlineKeyboardButton]] = []

    # Записи (участник)
    joined = await get_user_joined_events(session, user_id=user.id)
    if joined:
        lines += ["", "<b>Мои записи:</b>"]
        for ev in joined:
            lines.append(f"• {esc(ev.title)} — {format_datetime_msk(ev.starts_at)}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"❌ Отписаться: {esc(ev.title[:30])}",
                    callback_data=f"uleave:{ev.id}",
                )
            ])
    else:
        lines += ["", "Пока не записан ни на одно событие."]

    # Организованные события
    organized = await get_user_organized_events(session, user_id=user.id)
    if organized:
        lines += ["", "<b>Мои события (организатор):</b>"]
        for ev in organized:
            status_icon = "✅" if ev.status == "published" else "🕐"
            chat_mark = " · 💬" if ev.chat_url else ""
            lines.append(
                f"{status_icon} {esc(ev.title)}{chat_mark} — "
                f"{format_datetime_msk(ev.starts_at)}"
            )
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"👥 Участники: {esc(ev.title[:20])}",
                    callback_data=f"ep:{ev.id}",
                ),
                InlineKeyboardButton(
                    text="🚫 Отменить",
                    callback_data=f"ecancel:{ev.id}",
                ),
            ])
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"💬 Чат: {esc(ev.title[:24])}",
                    callback_data=f"evch:show:{ev.id}",
                ),
            ])

    # Мои отклики на чужие заявки
    responded = await get_user_responded_seekings(session, user_id=user.id)
    if responded:
        lines += ["", "<b>Мои отклики:</b>"]
        for sk in responded:
            lines.append(f"• {esc(sk.title)}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"❌ Убрать отклик: {esc(sk.title[:24])}",
                    callback_data=f"srd:{sk.id}",
                ),
            ])

    # Мои заявки «ищу компанию» (как автор)
    seekings = await get_user_seekings(session, author_id=user.id)
    if seekings:
        lines += ["", "<b>Мои заявки:</b>"]
        for sk in seekings:
            status_icon = "✅" if sk.status == "published" else "🕐"
            chat_mark = " · 💬" if sk.chat_url else ""
            lines.append(f"{status_icon} {esc(sk.title)}{chat_mark}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"👥 Отклики: {esc(sk.title[:20])}",
                    callback_data=f"skp:{sk.id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Закрыть",
                    callback_data=f"sk:close:{sk.id}",
                ),
            ])
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"💬 Чат: {esc(sk.title[:24])}",
                    callback_data=f"skch:show:{sk.id}",
                ),
            ])

    inline_rows.append([
        InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="profile:edit"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=inline_rows)


async def rerender_profile_card(
    callback_message,  # aiogram Message — оставляем свободным импортом, чтобы сервис не тащил типы
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
