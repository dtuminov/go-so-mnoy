"""Переиспользуемая карусель участников активности.

Используется и в профиле (`handlers/profile_nav.py` — кнопка «👥
Участники» внутри экрана деталей активности), и в ленте
(`handlers/activity.py` — кнопка «👥 Участники» на карточке ленты).

Разделение responsibility: этот модуль ничего не знает про то, откуда
пришёл пользователь. Вызывающая сторона передаёт `CarouselContext` с
шаблонами callback'ов для стрелок навигации и кнопки «назад», и этот
контекст вшивается в собираемую клавиатуру.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import MEMBER_JOINED
from bot.models import Activity, User
from bot.services.activities import get_activity, get_activity_members
from bot.services.users import get_user_by_id
from bot.utils.formatting import esc


# Нейтральный no-op для центральной кнопки пагинации «N/M». Хэндлер
# лежит в profile_nav.py и подключён глобально — работает из любого
# места, где рисуется карусель.
_NOOP_CB = "prf:noop"


@dataclass
class CarouselContext:
    """Контекст кнопок карусели.

    `nav_cb_template`:
        шаблон callback_data стрелок, с плейсхолдером `{idx}`. Например
        `"prf:mem:part:0:123:{idx}"` или `"fmem:n:123:{idx}"`.
    `back_cb`:
        callback_data кнопки «назад»/«закрыть».
    `back_label`:
        текст этой кнопки — зависит от контекста («↩️ К активности» из
        профиля, «❌ Закрыть» из ленты).
    """

    nav_cb_template: str
    back_cb: str
    back_label: str


# ──────────────────────────── data ──────────────────────────────────────────


async def get_activity_carousel_members(
    session: AsyncSession,
    activity: Activity,
) -> list[tuple[User, bool]]:
    """Готовит список `(user, is_creator)` для карусели:
    сначала создатель, потом joined-члены в порядке вступления.

    Если создатель сам же оказался в `activity_members` со статусом
    joined — он не дублируется (первое вхождение — как creator).
    """
    result: list[tuple[User, bool]] = []

    creator = await get_user_by_id(session, activity.creator_id)
    if creator is not None:
        result.append((creator, True))

    joined_rows = await get_activity_members(
        session, activity_id=activity.id, status=MEMBER_JOINED,
    )
    for _member, user in joined_rows:
        if user.id == activity.creator_id:
            continue
        result.append((user, False))

    return result


# ──────────────────────────── rendering ─────────────────────────────────────


def _trim(text: str, n: int) -> str:
    return text[:n] + "…" if len(text) > n else text


def _format_caption(
    *,
    activity: Activity,
    user: User,
    is_creator: bool,
    index: int,
    total: int,
) -> str:
    name = esc(user.first_name or user.username or "—")
    badge = " · 🎙 Организатор" if is_creator else ""
    username_part = f"\n@{esc(user.username)}" if user.username else ""
    age_part = f"\nВозраст: {user.age}" if user.age else ""
    bio_block = f"\n\n{esc(user.bio)}" if user.bio else ""

    return (
        f"<b>👥 Участники «{esc(activity.title)}»</b>  ·  {index + 1}/{total}\n\n"
        f"<b>👤 {name}</b>{badge}"
        f"{username_part}"
        f"{age_part}"
        f"{bio_block}"
    )


async def build_member_carousel_view(
    session: AsyncSession,
    *,
    activity_id: int,
    member_index: int,
    context: CarouselContext,
) -> tuple[str | None, str, InlineKeyboardMarkup] | None:
    """Собирает один слайд карусели.

    Возвращает `(photo_file_id, caption, keyboard)` или `None`, если
    активности/участников нет. `photo_file_id` может быть `None`, если
    у конкретного участника не задан аватар — caller в этом случае
    рисует сообщение текстом.

    Индекс клэмпится в валидный диапазон, так что вызов с переполненным
    `member_index` вернёт последний слайд, а не упадёт.
    """
    activity = await get_activity(session, activity_id)
    if activity is None:
        return None

    members = await get_activity_carousel_members(session, activity)
    if not members:
        return None

    total = len(members)
    idx = max(0, min(member_index, total - 1))
    user, is_creator = members[idx]

    caption = _format_caption(
        activity=activity, user=user, is_creator=is_creator,
        index=idx, total=total,
    )

    prev_idx = max(0, idx - 1)
    next_idx = min(total - 1, idx + 1)
    rows: list[list[InlineKeyboardButton]] = []

    if total > 1:
        rows.append([
            InlineKeyboardButton(
                text="⬅️",
                callback_data=context.nav_cb_template.format(idx=prev_idx),
            ),
            InlineKeyboardButton(
                text=f"{idx + 1}/{total}",
                callback_data=_NOOP_CB,
            ),
            InlineKeyboardButton(
                text="➡️",
                callback_data=context.nav_cb_template.format(idx=next_idx),
            ),
        ])

    if user.telegram_id:
        name = user.first_name or user.username or "—"
        rows.append([InlineKeyboardButton(
            text=f"💬 Написать {_trim(name, 18)}",
            url=f"tg://user?id={user.telegram_id}",
        )])

    rows.append([InlineKeyboardButton(
        text=context.back_label,
        callback_data=context.back_cb,
    )])

    return user.avatar_file_id, caption, InlineKeyboardMarkup(inline_keyboard=rows)
