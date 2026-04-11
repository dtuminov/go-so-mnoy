"""Навигация внутри профиля: хаб → секция → детали активности → карусель участников.

Всё живёт в одном фото-сообщении. Для хаба/секций/деталей фото =
аватар самого юзера; в карусели участников подменяем его на аватар
конкретного участника через `edit_message_media`. Возврат назад тоже
идёт через `edit_message_media`, чтобы вернуть «своё» фото.

Callback-префикс `prf:*` используется только здесь и не пересекается
с действиями над активностями (`al:`, `acan:`, …) — те остаются в
`handlers/activity.py` и после успеха вызывают `rerender_profile_to_hub`
(возврат на обзор).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InputMediaPhoto
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.activities import get_activity
from bot.services.cover import edit_to_activity_cover
from bot.services.member_carousel import (
    CarouselContext,
    build_member_carousel_view,
)
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


async def _nav_edit(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup,
    photo_file_id: str | None = None,
) -> None:
    """Единая точка перерисовки профиль-сообщения.

    Если исходное сообщение — фото **и** задан `photo_file_id`, делаем
    `edit_media` (меняем и картинку, и caption — нужно для навигации
    «карусель участников ↔ детали»). Если фото есть, а `photo_file_id`
    нет — обновляем только caption. Если исходно это текст — `edit_text`.

    Все ошибки Telegram (message is not modified, устаревшее сообщение
    и т.п.) глушим — UX это не ломает.
    """
    if callback.message is None:
        return
    try:
        if callback.message.photo and photo_file_id:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=photo_file_id,
                    caption=text,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=reply_markup,
            )
        elif callback.message.photo:
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
    await _nav_edit(
        callback, text=text, reply_markup=kb,
        photo_file_id=user.avatar_file_id,
    )
    await callback.answer()


# ──────────────────────────── section list ──────────────────────────────────


@router.callback_query(F.data == "prf:noop")
async def on_profile_noop(callback: CallbackQuery) -> None:
    """Пустой callback для центральной кнопки пагинации «N/M»."""
    await callback.answer()


@router.callback_query(F.data.startswith("prf:sec:"))
async def on_profile_section(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    # Формат: prf:sec:<section>[:<page>]
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    section = parts[2]
    if section not in _KNOWN_SECTIONS:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return
    page = 0
    if len(parts) >= 4:
        try:
            page = int(parts[3])
        except ValueError:
            page = 0

    user = await upsert_telegram_user(session, callback.from_user)
    text, kb = await build_section_view(
        session, user, section=section, page=page,
    )
    await _nav_edit(
        callback, text=text, reply_markup=kb,
        photo_file_id=user.avatar_file_id,
    )
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
    # Формат: prf:act:<section>:<page>:<id>
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    section = parts[2]
    try:
        page = int(parts[3])
        activity_id = int(parts[4])
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
        from_page=page,
    )
    if view is None:
        await callback.answer("Активность не найдена", show_alert=True)
        # Откатываемся к списку — там она тоже пропадёт.
        text, kb = await build_section_view(
            session, user, section=section, page=page,
        )
        await _nav_edit(
            callback, text=text, reply_markup=kb,
            photo_file_id=user.avatar_file_id,
        )
        return
    text, kb = view

    # На экране деталей фон — обложка самой активности (или дефолт),
    # а не аватар юзера. Идём через cover-сервис, который сам решит,
    # какой file_id или FSInputFile подставить.
    if callback.message is not None:
        activity = await get_activity(session, activity_id)
        await edit_to_activity_cover(
            callback.message,
            cover_file_id=activity.cover_file_id if activity else None,
            caption=text,
            reply_markup=kb,
        )
    await callback.answer()


# ──────────────────────────── member carousel ──────────────────────────────


@router.callback_query(F.data.startswith("prf:mem:"))
async def on_profile_member(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    # Формат: prf:mem:<section>:<page>:<activity_id>:<member_idx>
    parts = callback.data.split(":")
    if len(parts) < 6:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    section = parts[2]
    try:
        from_page = int(parts[3])
        activity_id = int(parts[4])
        member_index = int(parts[5])
    except ValueError:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    if section not in _KNOWN_SECTIONS:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    context = CarouselContext(
        nav_cb_template=f"prf:mem:{section}:{from_page}:{activity_id}:{{idx}}",
        back_cb=f"prf:act:{section}:{from_page}:{activity_id}",
        back_label="↩️ К активности",
    )
    view = await build_member_carousel_view(
        session,
        activity_id=activity_id,
        member_index=member_index,
        context=context,
    )
    if view is None:
        await callback.answer("Участников пока нет.", show_alert=True)
        return
    photo_id, text, kb = view
    await _nav_edit(
        callback, text=text, reply_markup=kb,
        photo_file_id=photo_id,
    )
    await callback.answer()
