from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.tag_picker import format_tags_inline
from bot.models import Event, Tag
from bot.utils.formatting import esc, format_datetime_msk


def _nav_callbacks(idx: int, total: int) -> tuple[str, str, str]:
    prev_idx = max(0, idx - 1)
    next_idx = min(total - 1, idx + 1)
    return (
        f"evp:g:{prev_idx}",
        f"evp:c:{idx}",
        f"evp:g:{next_idx}",
    )


def events_feed_keyboard(idx: int, total: int, event_id: int) -> InlineKeyboardMarkup:
    prev_cb, mid_cb, next_cb = _nav_callbacks(idx, total)
    cur = idx + 1
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="⬅️", callback_data=prev_cb),
            InlineKeyboardButton(text=f"{cur} / {total}", callback_data=mid_cb),
            InlineKeyboardButton(text="➡️", callback_data=next_cb),
        ],
        [InlineKeyboardButton(text="Иду ✅", callback_data=f"j:{event_id}")],
        [InlineKeyboardButton(text="🔎 Фильтры", callback_data="tp:e:open")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_event_card_text(event: Event, *, participants: int) -> str:
    """Карточка конкретного события — без шапки ленты."""
    tag_line = ""
    if event.tags:
        tag_line = f"\n🏷 {esc(format_tags_inline(list(event.tags)))}"
    return (
        f"<b>{esc(event.title)}</b>\n"
        f"{format_datetime_msk(event.starts_at)}\n"
        f"📍 {esc(event.place_text)}"
        f"{tag_line}\n"
        f"👥 Участников: {participants}\n\n"
        f"{esc(event.description)}"
    )


def format_event_feed_text(
    event: Event,
    *,
    participants: int,
    active_filter: list[Tag] | None = None,
) -> str:
    header = "<b>События в Москве</b>"
    if active_filter:
        header += f"\n<i>🔎 фильтр: {esc(format_tags_inline(active_filter))}</i>"
    return f"{header}\n\n{format_event_card_text(event, participants=participants)}"
