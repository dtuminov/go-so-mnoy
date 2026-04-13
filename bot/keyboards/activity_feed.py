"""Клавиатуры и форматирование карточек для ленты `Activity`.

Одна карточка = одна активность; навигация — пагинация по индексу.
Кнопка «💬 Чат» появляется только у тех, кто уже подтверждённый member
(`status='joined'`) и у активности задан `chat_url`.

Поскольку у нас две раздельные ленты («Найти событие» и «Найти компанию»),
`kind` пробрасывается в callback пагинации, чтобы листать в нужной ленте.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import ACTIVITY_EVENT
from bot.keyboards.tag_picker import format_tags_inline
from bot.models import Activity, Tag
from urllib.parse import quote

from bot.utils.formatting import esc, format_datetime_msk


def _filter_namespace(kind: str) -> str:
    """Сохраняем существующие namespaces фильтров: `tp:e:` для events,
    `tp:s:` для seekings."""
    return "tp:e:open" if kind == ACTIVITY_EVENT else "tp:s:open"


def _join_button_text(kind: str) -> str:
    return "Иду ✅" if kind == ACTIVITY_EVENT else "Хочу ✅"


def _create_button(kind: str) -> InlineKeyboardButton | None:
    if kind == ACTIVITY_EVENT:
        return None  # отдельная reply-кнопка в главном меню
    return InlineKeyboardButton(text="➕ Предложить своё", callback_data="sk:create")


def activity_feed_keyboard(
    idx: int,
    total: int,
    activity_id: int,
    *,
    kind: str,
    chat_url: str | None = None,
    viewer_joined: bool = False,
    viewer_pending: bool = False,
) -> InlineKeyboardMarkup:
    prev_idx = max(0, idx - 1)
    next_idx = min(total - 1, idx + 1)
    cur = idx + 1

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="⬅️", callback_data=f"af:g:{kind}:{prev_idx}"),
            InlineKeyboardButton(text=f"{cur} / {total}", callback_data=f"af:c:{kind}:{idx}"),
            InlineKeyboardButton(text="➡️", callback_data=f"af:g:{kind}:{next_idx}"),
        ],
    ]
    if viewer_joined:
        rows.append([InlineKeyboardButton(text="❌ Отписаться", callback_data=f"al:{activity_id}")])
    elif viewer_pending:
        rows.append([InlineKeyboardButton(text="⏳ Заявка отправлена · Отозвать", callback_data=f"al:{activity_id}")])
    else:
        rows.append([InlineKeyboardButton(text=_join_button_text(kind), callback_data=f"aj:{activity_id}")])

    # «💬 Чат» (если виден) и «👥 Участники» — в одном ряду пополам.
    # Если чата нет — «Участники» одни на ряд.
    members_btn = InlineKeyboardButton(
        text="👥 Участники",
        callback_data=f"fmem:o:{activity_id}",
    )
    if viewer_joined and chat_url:
        rows.append([
            InlineKeyboardButton(text="💬 Чат", url=chat_url),
            members_btn,
        ])
    else:
        rows.append([members_btn])

    bottom: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="🔎 Фильтры", callback_data=_filter_namespace(kind)),
    ]
    create = _create_button(kind)
    if create is not None:
        bottom.append(create)
    rows.append(bottom)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_activity_card_text(
    activity: Activity,
    *,
    members: int,
    author_name: str | None = None,
    author_age: int | None = None,
) -> str:
    """Карточка одной активности — без шапки ленты.

    `author_name` / `author_age` нужны только для seeking-карточек, чтобы
    показать «лицо» автора заявки. Caller обязан подгрузить creator
    отдельным запросом и пробросить значения сюда — формат нарочно не
    тащит ORM-лоадинг внутрь себя.
    """
    tag_line = ""
    if activity.tags:
        tag_line = f"\n🏷 {esc(format_tags_inline(list(activity.tags)))}"
    visibility_mark = " 🔒" if activity.visibility == "private" else ""

    author_line = ""
    if author_name:
        age_part = f", {author_age} лет" if author_age else ""
        author_line = f"\n👤 {esc(author_name)}{age_part}"

    if activity.kind == ACTIVITY_EVENT:
        when_line = format_datetime_msk(activity.starts_at)
        if activity.place_text:
            maps_url = f"https://yandex.ru/maps/?text={quote(activity.place_text)}"
            place_line = f'\n📍 <a href="{maps_url}">{esc(activity.place_text)}</a>'
        else:
            place_line = ""
        members_line = f"\n👥 Участников: {members}"
    else:
        when_line = f"⏳ до {format_datetime_msk(activity.expires_at)}"
        place_line = ""
        members_line = f"\n🙋 Откликов: {members}"

    body_block = f"\n\n{esc(activity.body)}" if activity.body else ""

    return (
        f"<b>{esc(activity.title)}</b>{visibility_mark}"
        f"{author_line}\n"
        f"{when_line}"
        f"{place_line}"
        f"{tag_line}"
        f"{members_line}"
        f"{body_block}"
    )


def format_activity_feed_text(
    activity: Activity,
    *,
    members: int,
    active_filter: list[Tag] | None = None,
    author_name: str | None = None,
    author_age: int | None = None,
    city_name: str = "",
) -> str:
    city = esc(city_name) if city_name else "Москва"
    if activity.kind == ACTIVITY_EVENT:
        header = f"<b>События · {city}</b>"
    else:
        header = f"<b>Ищут компанию · {city}</b>"
    if active_filter:
        header += f"\n<i>🔎 фильтр: {esc(format_tags_inline(active_filter))}</i>"
    return (
        f"{header}\n\n"
        + format_activity_card_text(
            activity,
            members=members,
            author_name=author_name,
            author_age=author_age,
        )
    )
