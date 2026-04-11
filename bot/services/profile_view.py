"""Сборка экранов профиля: хаб → список секции → детали активности.

Всё живёт в одном фото-сообщении (аватар юзера), навигация — через
`edit_caption`. Управляющие callback-и (prf:*) — в
`bot/handlers/profile_nav.py`.

Сознательно избегаем FSM-стейта для навигации — текущий экран
закодирован в callback_data кнопок («вернуться в секцию X»).
"""

from __future__ import annotations

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import (
    ACTIVITY_EVENT,
    VISIBILITY_PRIVATE,
)
from bot.keyboards.tag_picker import format_tags_inline
from bot.models import Activity, User
from bot.services.activities import (
    count_joined_members,
    count_pending_members,
    get_activities_with_incoming_pending,
    get_activity,
    get_activity_members,
    get_creator_summary,
    get_user_created_activities,
    get_user_joined_activities,
    get_user_pending_activities,
    get_user_role_in_activity,
)
from bot.utils.formatting import esc, format_datetime_msk

# ──────────────────────────── sections enum ─────────────────────────────────

SECTION_PARTICIPATING = "part"
SECTION_CREATED = "cre"
SECTION_INCOMING_PENDING = "incp"  # заявки ждут моего решения
SECTION_OUTGOING_PENDING = "outp"  # я жду решения

# Размер страницы списка в секции профиля. Текст и кнопки рендерятся
# батчем по `SECTION_PAGE_SIZE` элементов, навигация между страницами —
# отдельным рядом [← Назад] [N/M] [Далее →] под кнопками активностей.
SECTION_PAGE_SIZE = 5


# ──────────────────────────── helpers ───────────────────────────────────────


def _kind_icon(activity: Activity) -> str:
    return "📍" if activity.kind == ACTIVITY_EVENT else "🤝"


def _visibility_mark(activity: Activity) -> str:
    return " 🔒" if activity.visibility == VISIBILITY_PRIVATE else ""


def _when_line(activity: Activity) -> str:
    """Короткая строка «когда» для списков."""
    if activity.kind == ACTIVITY_EVENT:
        return format_datetime_msk(activity.starts_at)
    return f"до {format_datetime_msk(activity.expires_at)}"


def _profile_header(user: User) -> list[str]:
    name = esc(user.first_name or user.username or "Ты")
    lines = [f"<b>👤 {name}</b>"]
    if user.age:
        lines.append(f"Возраст: {user.age}")
    if user.bio:
        lines += ["", esc(user.bio)]
    return lines


def _trim(text: str, n: int) -> str:
    return text[:n] + "…" if len(text) > n else text


# ──────────────────────────── HUB ───────────────────────────────────────────


async def build_hub_view(
    session: AsyncSession,
    user: User,
) -> tuple[str, InlineKeyboardMarkup]:
    """Экран-хаб профиля: короткая анкета + кнопки разделов с бейджами.

    Пустые разделы не показываются вообще — чтобы не было шума.
    """
    lines = _profile_header(user)

    # Считаем заполненность разделов
    joined = await _count_joined(session, user.id)
    created = await _count_created(session, user.id)
    outgoing = await _count_outgoing_pending(session, user.id)
    incoming = await _count_incoming_pending(session, user.id)

    if joined + created + outgoing + incoming == 0:
        lines += ["", "<i>Пока ничего — загляни в ленту.</i>"]

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="profile:edit")],
    ]
    if joined:
        rows.append([InlineKeyboardButton(
            text=f"🎫 Я участвую ({joined})",
            callback_data=f"prf:sec:{SECTION_PARTICIPATING}",
        )])
    if created:
        rows.append([InlineKeyboardButton(
            text=f"🎙 Я создал ({created})",
            callback_data=f"prf:sec:{SECTION_CREATED}",
        )])
    if incoming:
        rows.append([InlineKeyboardButton(
            text=f"✋ Подтвердить участников ({incoming})",
            callback_data=f"prf:sec:{SECTION_INCOMING_PENDING}",
        )])
    if outgoing:
        rows.append([InlineKeyboardButton(
            text=f"⏳ Жду подтверждения ({outgoing})",
            callback_data=f"prf:sec:{SECTION_OUTGOING_PENDING}",
        )])

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _count_joined(session: AsyncSession, user_id: int) -> int:
    events = await get_user_joined_activities(session, user_id=user_id, kind=ACTIVITY_EVENT)
    from bot.constants import ACTIVITY_SEEKING
    seekings = await get_user_joined_activities(session, user_id=user_id, kind=ACTIVITY_SEEKING)
    return len(events) + len(seekings)


async def _count_created(session: AsyncSession, user_id: int) -> int:
    events = await get_user_created_activities(session, user_id=user_id, kind=ACTIVITY_EVENT)
    from bot.constants import ACTIVITY_SEEKING
    seekings = await get_user_created_activities(session, user_id=user_id, kind=ACTIVITY_SEEKING)
    return len(events) + len(seekings)


async def _count_outgoing_pending(session: AsyncSession, user_id: int) -> int:
    return len(await get_user_pending_activities(session, user_id=user_id))


async def _count_incoming_pending(session: AsyncSession, user_id: int) -> int:
    acts = await get_activities_with_incoming_pending(session, creator_id=user_id)
    return len(acts)


# ──────────────────────────── SECTION LISTS ─────────────────────────────────


def _back_row(to_callback: str, label: str = "↩️ Назад") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=label, callback_data=to_callback)]


async def _participating_activities(
    session: AsyncSession, user_id: int,
) -> list[Activity]:
    from bot.constants import ACTIVITY_SEEKING
    events = await get_user_joined_activities(session, user_id=user_id, kind=ACTIVITY_EVENT)
    seekings = await get_user_joined_activities(session, user_id=user_id, kind=ACTIVITY_SEEKING)
    merged = list(events) + list(seekings)
    merged.sort(key=lambda a: a.expires_at)
    return merged


async def _created_activities(
    session: AsyncSession, user_id: int,
) -> list[Activity]:
    from bot.constants import ACTIVITY_SEEKING
    events = await get_user_created_activities(session, user_id=user_id, kind=ACTIVITY_EVENT)
    seekings = await get_user_created_activities(session, user_id=user_id, kind=ACTIVITY_SEEKING)
    merged = list(events) + list(seekings)
    merged.sort(key=lambda a: a.expires_at)
    return merged


async def build_section_view(
    session: AsyncSession,
    user: User,
    *,
    section: str,
    page: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    """Список активностей внутри выбранного раздела с пагинацией по
    `SECTION_PAGE_SIZE` элементов. Один ряд на активность — inline-
    кнопка с коротким названием, клик ведёт в детали
    (`prf:act:<section>:<page>:<id>`). Под кнопками — ряд
    [← Назад] [N/M] [Далее →], если страниц больше одной.
    """
    if section == SECTION_PARTICIPATING:
        title = "🎫 Я участвую"
        activities = await _participating_activities(session, user.id)
        empty = "Пока нигде не участвую."
    elif section == SECTION_CREATED:
        title = "🎙 Я создал"
        activities = await _created_activities(session, user.id)
        empty = "Пока ничего не создавал."
    elif section == SECTION_INCOMING_PENDING:
        title = "✋ Подтвердить участников"
        activities = await get_activities_with_incoming_pending(
            session, creator_id=user.id,
        )
        empty = "Никто не ждёт твоего подтверждения."
    elif section == SECTION_OUTGOING_PENDING:
        title = "⏳ Жду подтверждения"
        activities = await get_user_pending_activities(session, user_id=user.id)
        empty = "Нет активных заявок на чужие активности."
    else:
        title = "Неизвестный раздел"
        activities = []
        empty = ""

    total = len(activities)
    total_pages = max(1, (total + SECTION_PAGE_SIZE - 1) // SECTION_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * SECTION_PAGE_SIZE
    end = start + SECTION_PAGE_SIZE
    page_items = activities[start:end]

    # ── текст ───────────────────────────────────────────────────────────────
    header = f"<b>{title}</b>"
    if total_pages > 1:
        header += f"  ·  стр. {page + 1}/{total_pages}"
    lines = [header]
    if not activities:
        lines += ["", f"<i>{empty}</i>"]
    else:
        lines.append("")
        for offset, act in enumerate(page_items):
            absolute_idx = start + offset + 1
            icon = _kind_icon(act)
            vis = _visibility_mark(act)
            when = _when_line(act)
            extras: list[str] = []
            if section == SECTION_INCOMING_PENDING:
                n = await count_pending_members(session, act.id)
                extras.append(f"⏳ {n}")
            lines.append(
                f"{absolute_idx}. {icon} {esc(act.title)}{vis} — {when}"
                + (f"  ·  {' · '.join(extras)}" if extras else "")
            )

    # ── клавиатура ──────────────────────────────────────────────────────────
    rows: list[list[InlineKeyboardButton]] = []
    for act in page_items:
        icon = _kind_icon(act)
        label = f"{icon} {_trim(act.title, 24)}"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"prf:act:{section}:{page}:{act.id}",
        )])

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"prf:sec:{section}:{page - 1}",
            ))
        nav.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="prf:noop",
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                text="Далее ➡️",
                callback_data=f"prf:sec:{section}:{page + 1}",
            ))
        rows.append(nav)

    rows.append(_back_row("prf:hub", label="↩️ В меню"))

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


# ──────────────────────────── ACTIVITY DETAIL ────────────────────────────────


async def _detail_body(
    session: AsyncSession,
    activity: Activity,
) -> str:
    """Тело карточки активности в экране деталей — детальнее, чем
    строка в списке: теги, участники/отклики, автор (для seeking),
    описание."""
    lines: list[str] = []
    header_icon = _kind_icon(activity)
    vis_mark = _visibility_mark(activity)
    lines.append(f"<b>{header_icon} {esc(activity.title)}</b>{vis_mark}")

    if activity.kind == ACTIVITY_EVENT:
        lines.append(format_datetime_msk(activity.starts_at))
        if activity.place_text:
            lines.append(f"📍 {esc(activity.place_text)}")
    else:
        lines.append(f"⏳ до {format_datetime_msk(activity.expires_at)}")

    if activity.tags:
        lines.append(f"🏷 {esc(format_tags_inline(list(activity.tags)))}")

    # Для seeking — показываем автора, как в ленте.
    if activity.kind != ACTIVITY_EVENT:
        author_name, author_age = await get_creator_summary(session, activity)
        if author_name:
            age_part = f", {author_age} лет" if author_age else ""
            lines.append(f"👤 {esc(author_name)}{age_part}")

    joined_count = await count_joined_members(session, activity.id)
    pending_count = await count_pending_members(session, activity.id)
    if activity.kind == ACTIVITY_EVENT:
        members_line = f"👥 Участников: {joined_count}"
    else:
        members_line = f"🙋 Откликов: {joined_count}"
    if pending_count:
        members_line += f"  ·  ⏳ Ждут: {pending_count}"
    lines.append(members_line)

    if activity.chat_url:
        lines.append("💬 Чат: настроен")

    if activity.body:
        lines += ["", esc(activity.body)]

    return "\n".join(lines)


async def build_activity_detail_view(
    session: AsyncSession,
    user: User,
    *,
    activity_id: int,
    from_section: str,
    from_page: int = 0,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Экран деталей одной активности в контексте профиля.

    Набор кнопок управления зависит от роли пользователя относительно
    активности: creator / joined / pending / none.

    Возвращает `None`, если активности не существует — хэндлер покажет
    alert и вернёт юзера в секцию.
    """
    activity = await get_activity(session, activity_id)
    if activity is None:
        return None

    role = await get_user_role_in_activity(
        session, activity=activity, user_id=user.id,
    )
    text = await _detail_body(session, activity)

    rows: list[list[InlineKeyboardButton]] = []

    if role == "creator":
        # Управление своей активностью.
        rows.append([
            InlineKeyboardButton(text="👥 Участники", callback_data=f"amem:{activity.id}"),
            InlineKeyboardButton(text="💬 Чат", callback_data=f"actch:show:{activity.id}"),
        ])
        rows.append([
            InlineKeyboardButton(text="🔒 Доступ", callback_data=f"avis:show:{activity.id}"),
        ])
        if activity.kind == ACTIVITY_EVENT:
            rows.append([
                InlineKeyboardButton(text="🚫 Отменить событие", callback_data=f"acan:{activity.id}"),
            ])
        else:
            rows.append([
                InlineKeyboardButton(text="🗑 Закрыть заявку", callback_data=f"aclose:{activity.id}"),
            ])

    elif role == "joined":
        if activity.chat_url:
            rows.append([
                InlineKeyboardButton(text="💬 Открыть чат", url=activity.chat_url),
            ])
        if activity.kind == ACTIVITY_EVENT:
            leave_label = "❌ Отписаться"
        else:
            leave_label = "❌ Убрать отклик"
        rows.append([
            InlineKeyboardButton(text=leave_label, callback_data=f"al:{activity.id}"),
        ])

    elif role == "pending":
        text += "\n\n<i>⏳ Ждёт подтверждения организатора.</i>"
        rows.append([
            InlineKeyboardButton(text="↩️ Отозвать заявку", callback_data=f"al:{activity.id}"),
        ])

    rows.append(_back_row(f"prf:sec:{from_section}:{from_page}"))

    return text, InlineKeyboardMarkup(inline_keyboard=rows)


# ──────────────────────────── rerender helpers ──────────────────────────────


async def rerender_profile_to_hub(
    callback_message,
    session: AsyncSession,
    user: User,
) -> None:
    """Перерисовывает профильное фото-сообщение на актуальный хаб.

    Используется после успешных мутаций (leave / cancel / close / etc.),
    пришедших из профиля, — возвращает юзера на обзор с обновлёнными
    счётчиками.
    """
    text, kb = await build_hub_view(session, user)
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
        # Сообщение могло устареть — не критично, при следующем открытии
        # профиля пересоберётся.
        pass


# Backward-compat alias, чтобы не ломать существующие импорты из
# handlers/activity.py — старое название переадресуем в новый хаб.
rerender_profile_card = rerender_profile_to_hub
