"""Универсальная клавиатура-пикер тегов с мульти-выбором.

Callback-префикс задаётся вызывающей стороной (чтобы один и тот же пикер можно
было использовать и для фильтрации ленты, и для шага в FSM создания события
или заявки — без коллизий роутов).

Форматы callback_data:
    {prefix}:t:{tag_id}  — toggle конкретного тега
    {prefix}:apply       — применить выбор (для фильтров)
    {prefix}:clear       — сбросить выбор
    {prefix}:cancel      — отмена
    {prefix}:done        — закончить выбор (для flow создания)

Кнопки «apply/clear/cancel/done» рендерит вызывающая сторона через флаги.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.models import Tag


def _tag_button(
    *,
    tag: Tag,
    selected: bool,
    prefix: str,
) -> InlineKeyboardButton:
    mark = "✅ " if selected else ""
    label = f"{mark}{tag.emoji} {tag.name}".strip()
    return InlineKeyboardButton(
        text=label,
        callback_data=f"{prefix}:t:{tag.id}",
    )


def tag_picker_keyboard(
    *,
    tags: list[Tag],
    selected_ids: set[int],
    prefix: str,
    with_apply: bool = False,
    with_clear: bool = False,
    with_cancel: bool = False,
    with_done: bool = False,
    columns: int = 2,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for t in tags:
        row.append(_tag_button(tag=t, selected=t.id in selected_ids, prefix=prefix))
        if len(row) >= columns:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    controls: list[InlineKeyboardButton] = []
    if with_apply:
        controls.append(
            InlineKeyboardButton(text="✅ Применить", callback_data=f"{prefix}:apply"),
        )
    if with_done:
        controls.append(
            InlineKeyboardButton(text="✅ Готово", callback_data=f"{prefix}:done"),
        )
    if with_clear:
        controls.append(
            InlineKeyboardButton(text="🗑 Сбросить", callback_data=f"{prefix}:clear"),
        )
    if with_cancel:
        controls.append(
            InlineKeyboardButton(text="✖️ Отмена", callback_data=f"{prefix}:cancel"),
        )
    if controls:
        rows.append(controls)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_tags_inline(tags: list[Tag]) -> str:
    """Одна строка через «·», для шапки карточки / активного фильтра."""
    if not tags:
        return ""
    return " · ".join(f"{t.emoji} {t.name}" for t in tags)
