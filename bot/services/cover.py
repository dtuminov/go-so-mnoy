"""Обложка активности: единая точка отправки и редактирования
фото-сообщения с обложкой `Activity`.

Если у активности задан `cover_file_id` (Telegram file_id, юзер
загрузил картинку при создании или сменил позже) — используем его.
Иначе показываем дефолтную обложку из `bot/assets/`. Дефолтная
обложка кэшируется в памяти после первой отправки: aiogram заливает
её через `FSInputFile`, мы выдёргиваем `file_id` из ответа и дальше
все показы дефолта используют этот строковый file_id (без
повторных аплоадов).

Кэш живёт до рестарта бота. После рестарта первый показ снова
зальёт файл и снова закэширует. Это нормально для MVP.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram.enums import ParseMode
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

logger = logging.getLogger(__name__)


# Путь к дефолтной обложке относительно корня пакета `bot/`.
DEFAULT_ACTIVITY_COVER_PATH: Path = (
    Path(__file__).resolve().parent.parent / "assets" / "default_activity_cover.png"
)


# In-memory кэш для file_id дефолтной обложки. None → ещё не заливали
# (или бот только что перезапустился), на первой отправке зальём через
# FSInputFile и сохраним сюда file_id из ответа Telegram.
_default_cover_file_id: str | None = None


def _resolve_payload(activity_cover_file_id: str | None) -> tuple[str | FSInputFile, bool]:
    """Возвращает `(payload, is_default_first_upload)`.

    `payload` — то, что нужно положить в `photo=` / `InputMediaPhoto.media=`:
    либо строковый file_id (кастомная обложка или уже закэшированный
    дефолт), либо `FSInputFile` дефолтной обложки (первый раз).

    `is_default_first_upload` = True, если это первый upload дефолта
    и нужно после успешной отправки выдернуть file_id и закэшировать.
    """
    if activity_cover_file_id:
        return activity_cover_file_id, False
    if _default_cover_file_id:
        return _default_cover_file_id, False
    if not DEFAULT_ACTIVITY_COVER_PATH.exists():
        # Конфигурационная ошибка — фоллбэк просто на пустой file_id
        # вызовет AttributeError позже; лучше явно зашуметь.
        raise FileNotFoundError(
            f"Default cover not found at {DEFAULT_ACTIVITY_COVER_PATH}",
        )
    return FSInputFile(DEFAULT_ACTIVITY_COVER_PATH), True


def _maybe_cache_from_message(message: Message | None, was_first_upload: bool) -> None:
    """Если это была первая отправка дефолта через FSInputFile —
    выдёргиваем file_id из ответа Telegram и сохраняем."""
    global _default_cover_file_id
    if not was_first_upload:
        return
    if message is None or not message.photo:
        return
    _default_cover_file_id = message.photo[-1].file_id
    logger.info("default cover cached as file_id=%s", _default_cover_file_id)


# ──────────────────────────── public API ────────────────────────────────────


async def send_activity_cover(
    target: Message,
    *,
    cover_file_id: str | None,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Отправляет новое фото-сообщение с обложкой активности (или
    дефолтом, если своя не задана). Возвращает Message — на случай
    если caller хочет потом редактировать его."""
    payload, first_upload = _resolve_payload(cover_file_id)
    sent = await target.answer_photo(
        photo=payload,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
    _maybe_cache_from_message(sent, first_upload)
    return sent


async def edit_to_activity_cover(
    message: Message,
    *,
    cover_file_id: str | None,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Меняет существующее фото-сообщение на обложку активности
    (через `edit_message_media`). Глотает Telegram-ошибки
    («message is not modified», устаревшее сообщение и т.п.)."""
    payload, first_upload = _resolve_payload(cover_file_id)
    try:
        result = await message.edit_media(
            media=InputMediaPhoto(
                media=payload,
                caption=caption,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=reply_markup,
        )
    except Exception:
        return
    if isinstance(result, Message):
        _maybe_cache_from_message(result, first_upload)
