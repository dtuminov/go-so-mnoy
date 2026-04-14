"""Модерация активностей: список pending_review, approve / reject.
Создание шаблонов для deep link из канала.
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from admin_bot.config import get_admin_settings
from bot.constants import (
    ACTIVITY_CANCELLED,
    ACTIVITY_CLOSED,
    ACTIVITY_PENDING_REVIEW,
    ACTIVITY_PUBLISHED,
    ACTIVITY_REJECTED,
)
from bot.models import Activity, ActivityMember, EventTemplate, User
from bot.utils.formatting import esc, format_datetime_msk

router = Router(name="moderation")


# ──────────────────────────── guard ──────────────────────────────────────────


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in get_admin_settings().admin_ids


# ──────────────────────────── helpers ────────────────────────────────────────


def _activity_card(activity: Activity, creator: User | None) -> str:
    kind_label = "Событие" if activity.is_event else "Ищу компанию"
    lines = [
        f"<b>{esc(activity.title)}</b>",
        f"Тип: {kind_label}  |  ID: {activity.id}",
    ]
    if creator:
        name = creator.first_name or creator.username or f"uid:{creator.id}"
        lines.append(f"Автор: {esc(name)} (tg:{creator.telegram_id})")
    if activity.body:
        body_preview = activity.body[:200]
        if len(activity.body) > 200:
            body_preview += "…"
        lines.append(f"\n{esc(body_preview)}")
    if activity.starts_at:
        lines.append(f"Начало: {format_datetime_msk(activity.starts_at)}")
    lines.append(f"Истекает: {format_datetime_msk(activity.expires_at)}")
    if activity.place_text:
        from urllib.parse import quote
        maps_url = f"https://yandex.ru/maps/?text={quote(activity.place_text)}"
        lines.append(f'Место: <a href="{maps_url}">{esc(activity.place_text)}</a>')
    if activity.tags:
        tag_names = ", ".join(t.name for t in activity.tags)
        lines.append(f"Теги: {esc(tag_names)}")
    lines.append(f"Видимость: {activity.visibility}")
    return "\n".join(lines)


def _decision_keyboard(activity_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=f"adm:apr:{activity_id}")
    kb.button(text="❌ Reject", callback_data=f"adm:rej:{activity_id}")
    kb.adjust(2)
    return kb


# ──────────────────────────── /start, /pending ───────────────────────────────


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await message.answer(
        "Админ-бот модерации.\n\n"
        "/pending — заявки на модерацию\n"
        "/stats — краткая статистика\n"
        "/users — список пользователей\n"
        "/activities — список всех активностей\n"
        "/delete <code>ID</code> — удалить активность\n\n"
        "<b>Шаблоны для канала:</b>\n"
        "/template — создать шаблон события\n"
        "/templates — список шаблонов с deep link",
    )


@router.message(Command("pending"))
async def cmd_pending(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    stmt = (
        select(Activity)
        .where(Activity.status == ACTIVITY_PENDING_REVIEW)
        .options(selectinload(Activity.tags))
        .order_by(Activity.created_at.asc())
        .limit(20)
    )
    result = await session.execute(stmt)
    activities = list(result.scalars().all())

    if not activities:
        await message.answer("Нет заявок на модерацию 🎉")
        return

    await message.answer(f"Заявок на модерации: <b>{len(activities)}</b>")

    creator_ids = {a.creator_id for a in activities}
    creators_result = await session.execute(
        select(User).where(User.id.in_(creator_ids))
    )
    creators_map = {u.id: u for u in creators_result.scalars().all()}

    for act in activities:
        creator = creators_map.get(act.creator_id)
        text = _activity_card(act, creator)
        kb = _decision_keyboard(act.id)
        await message.answer(text, reply_markup=kb.as_markup())


# ──────────────────────────── approve / reject ───────────────────────────────


@router.callback_query(F.data.startswith("adm:apr:"))
async def cb_approve(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    activity_id = int(callback.data.split(":")[2])
    activity = await session.get(Activity, activity_id)

    if activity is None:
        await callback.answer("Активность не найдена", show_alert=True)
        return
    if activity.status != ACTIVITY_PENDING_REVIEW:
        await callback.answer(
            f"Статус уже: {activity.status}", show_alert=True,
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    activity.status = ACTIVITY_PUBLISHED
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>APPROVED</b>",
        reply_markup=None,
    )
    await callback.answer("Опубликовано ✅")


@router.callback_query(F.data.startswith("adm:rej:"))
async def cb_reject(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    activity_id = int(callback.data.split(":")[2])
    activity = await session.get(Activity, activity_id)

    if activity is None:
        await callback.answer("Активность не найдена", show_alert=True)
        return
    if activity.status != ACTIVITY_PENDING_REVIEW:
        await callback.answer(
            f"Статус уже: {activity.status}", show_alert=True,
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    activity.status = ACTIVITY_REJECTED
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>REJECTED</b>",
        reply_markup=None,
    )
    await callback.answer("Отклонено ❌")


# ──────────────────────────── /stats ─────────────────────────────────────────


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    rows = await session.execute(
        select(Activity.status, func.count())
        .group_by(Activity.status)
    )
    counts = dict(rows.all())
    total = sum(counts.values())

    lines = [
        f"📊 <b>Статистика активностей</b> (всего: {total})",
        "",
        f"⏳ pending_review: {counts.get(ACTIVITY_PENDING_REVIEW, 0)}",
        f"✅ published: {counts.get(ACTIVITY_PUBLISHED, 0)}",
        f"❌ rejected: {counts.get(ACTIVITY_REJECTED, 0)}",
        f"🚫 cancelled: {counts.get(ACTIVITY_CANCELLED, 0)}",
        f"🔒 closed: {counts.get(ACTIVITY_CLOSED, 0)}",
    ]
    await message.answer("\n".join(lines))


# ──────────────────────────── /users ─────────────────────────────────────────


@router.message(Command("users"))
async def cmd_users(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    result = await session.execute(
        select(User).order_by(User.created_at.desc()).limit(50)
    )
    users = list(result.scalars().all())

    if not users:
        await message.answer("Пользователей нет.")
        return

    lines = [f"👥 <b>Пользователи</b> ({len(users)})\n"]
    for u in users:
        name = u.first_name or u.username or "—"
        username_part = f" @{u.username}" if u.username else ""
        age_part = f", {u.age} лет" if u.age else ""
        profile = "✅" if u.bio else "—"
        lines.append(
            f"<b>{u.id}</b>. {esc(name)}{username_part}{age_part}"
            f" | tg:{u.telegram_id} | профиль: {profile}"
        )

    text = "\n".join(lines)
    # Telegram ограничивает 4096 символов
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>…обрезано</i>"
    await message.answer(text)


# ──────────────────────────── /activities ─────────────────────────────────────


STATUS_ICON = {
    ACTIVITY_PENDING_REVIEW: "⏳",
    ACTIVITY_PUBLISHED: "✅",
    ACTIVITY_REJECTED: "❌",
    ACTIVITY_CANCELLED: "🚫",
    ACTIVITY_CLOSED: "🔒",
}


@router.message(Command("activities"))
async def cmd_activities(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    result = await session.execute(
        select(Activity).order_by(Activity.created_at.desc()).limit(50)
    )
    activities = list(result.scalars().all())

    if not activities:
        await message.answer("Активностей нет.")
        return

    lines = [f"📋 <b>Активности</b> ({len(activities)})\n"]
    for a in activities:
        kind = "🎉" if a.is_event else "🤝"
        icon = STATUS_ICON.get(a.status, "?")
        title_short = a.title[:40] + ("…" if len(a.title) > 40 else "")
        lines.append(
            f"{icon} <b>{a.id}</b>. {kind} {esc(title_short)}"
            f" | {a.status}"
        )

    lines.append("\nУдалить: /delete <code>ID</code>")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>…обрезано</i>"
    await message.answer(text)


# ──────────────────────────── /delete ─────────────────────────────────────────


@router.message(Command("delete"))
async def cmd_delete(
    message: Message, command: CommandObject, session: AsyncSession,
) -> None:
    if not _is_admin(message.from_user.id):
        return

    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /delete <code>ID</code>")
        return

    activity_id = int(command.args.strip())
    activity = await session.get(Activity, activity_id)

    if activity is None:
        await message.answer(f"Активность #{activity_id} не найдена.")
        return

    kind_label = "Событие" if activity.is_event else "Ищу компанию"
    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"🗑 Да, удалить #{activity_id}",
        callback_data=f"adm:del:{activity_id}",
    )
    kb.button(text="Отмена", callback_data="adm:del:cancel")
    kb.adjust(1)

    await message.answer(
        f"Удалить активность?\n\n"
        f"<b>{esc(activity.title)}</b>\n"
        f"Тип: {kind_label} | ID: {activity_id} | Статус: {activity.status}",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("adm:del:"))
async def cb_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    payload = callback.data.split(":")[2]

    if payload == "cancel":
        await callback.message.edit_text("Удаление отменено.")
        await callback.answer()
        return

    activity_id = int(payload)
    activity = await session.get(Activity, activity_id)

    if activity is None:
        await callback.answer("Активность уже удалена", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    title = activity.title
    await session.execute(
        delete(ActivityMember).where(ActivityMember.activity_id == activity_id)
    )
    await session.delete(activity)

    await callback.message.edit_text(
        f"🗑 Удалено: <b>{esc(title)}</b> (ID: {activity_id})",
        reply_markup=None,
    )
    await callback.answer("Удалено 🗑")


# ──────────────────────────── event templates ─────────────────────────────────


class TemplateSG(StatesGroup):
    title = State()
    place = State()
    cover = State()
    description = State()


@router.message(Command("template"), StateFilter(default_state))
async def cmd_template(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(TemplateSG.title)
    await message.answer("Название шаблона (например, «Йога на Арбате»):")


@router.message(TemplateSG.title, F.text)
async def template_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("Минимум 3 символа.")
        return
    await state.update_data(tpl_title=title[:255])
    await state.set_state(TemplateSG.place)

    from bot.config import get_settings
    api_key = get_settings().twogis_api_key
    if api_key:
        await message.answer(
            "Место (адрес или название) — будут подсказки 2GIS.\n"
            "Или /skip чтобы оставить пустым.",
        )
    else:
        await message.answer("Место (адрес). Или /skip чтобы пропустить:")


@router.message(TemplateSG.place, Command("skip"))
async def template_place_skip(message: Message, state: FSMContext) -> None:
    await state.update_data(tpl_place="")
    await state.set_state(TemplateSG.cover)
    await message.answer("Обложка — отправь фото. Или /skip:")


@router.message(TemplateSG.place, F.text)
async def template_place(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if len(raw) < 2:
        await message.answer("Укажи место подробнее.")
        return

    from bot.config import get_settings
    api_key = get_settings().twogis_api_key
    if api_key:
        from bot.services.place_suggest import suggest_places
        suggestions = await suggest_places(raw, api_key, count=4)
        if suggestions:
            fulls = [s.full for s in suggestions]
            await state.update_data(_tpl_suggestions=fulls, _tpl_place_raw=raw)
            rows = [
                [InlineKeyboardButton(text=s.name[:60], callback_data=f"tplp:{i}")]
                for i, s in enumerate(suggestions)
            ]
            keep_label = f"✅ Оставить «{raw[:30]}»"
            rows.append([InlineKeyboardButton(text=keep_label, callback_data="tplp:keep")])
            await message.answer(
                "Выбери место:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
            return

    await state.update_data(tpl_place=raw[:512])
    await state.set_state(TemplateSG.cover)
    await message.answer("Обложка — отправь фото. Или /skip:")


@router.callback_query(F.data.startswith("tplp:"), StateFilter(TemplateSG.place))
async def template_place_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    choice = callback.data.split(":", 1)[1]

    if choice == "keep":
        place = data.get("_tpl_place_raw", "")
    else:
        try:
            idx = int(choice)
        except ValueError:
            await callback.answer()
            return
        suggestions = data.get("_tpl_suggestions", [])
        if idx < 0 or idx >= len(suggestions):
            await callback.answer()
            return
        place = suggestions[idx]

    await state.update_data(tpl_place=place[:512])
    await state.set_state(TemplateSG.cover)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Обложка — отправь фото. Или /skip:")


@router.message(TemplateSG.cover, Command("skip"))
async def template_cover_skip(message: Message, state: FSMContext) -> None:
    await state.set_state(TemplateSG.description)
    await message.answer("Описание (опционально). Или /skip:")


@router.message(TemplateSG.cover, F.photo)
async def template_cover(message: Message, state: FSMContext) -> None:
    photos = message.photo
    if not photos:
        await message.answer("Отправь фото.")
        return
    await state.update_data(tpl_cover=photos[-1].file_id)
    await state.set_state(TemplateSG.description)
    await message.answer("Описание (опционально). Или /skip:")


@router.message(TemplateSG.cover)
async def template_cover_wrong(message: Message) -> None:
    await message.answer("Отправь фото или /skip.")


@router.message(TemplateSG.description, Command("skip"))
async def template_desc_skip(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await _save_template(message, state, session, description=None)


@router.message(TemplateSG.description, F.text)
async def template_desc(message: Message, state: FSMContext, session: AsyncSession) -> None:
    desc = (message.text or "").strip()
    await _save_template(message, state, session, description=desc or None)


async def _save_template(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    description: str | None,
) -> None:
    data = await state.get_data()
    title = data.get("tpl_title", "")
    place = data.get("tpl_place", "")
    cover = data.get("tpl_cover")

    tpl = EventTemplate(
        title=title, place_text=place, description=description,
        cover_file_id=cover,
    )
    session.add(tpl)
    await session.flush()

    bot_username = get_admin_settings().main_bot_username
    if not bot_username:
        from bot.config import get_settings
        bot_username = get_settings().bot_username or "bot"
    link = f"https://t.me/{bot_username}?start=tpl_{tpl.id}"

    await state.clear()
    await message.answer(
        f"✅ Шаблон создан!\n\n"
        f"<b>{esc(title)}</b>\n"
        f"📍 {esc(place) if place else '—'}\n\n"
        f"Deep link для канала:\n<code>{link}</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("templates"))
async def cmd_templates(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return
    result = await session.execute(
        select(EventTemplate).order_by(EventTemplate.id.desc()).limit(20),
    )
    templates = list(result.scalars().all())
    if not templates:
        await message.answer("Шаблонов нет. Создай: /template")
        return

    bot_username = get_admin_settings().main_bot_username
    if not bot_username:
        from bot.config import get_settings
        bot_username = get_settings().bot_username or "bot"

    lines = ["<b>Шаблоны событий:</b>\n"]
    for t in templates:
        link = f"https://t.me/{bot_username}?start=tpl_{t.id}"
        place_part = f" · {esc(t.place_text)}" if t.place_text else ""
        lines.append(f"{t.id}. <b>{esc(t.title)}</b>{place_part}\n<code>{link}</code>")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)
