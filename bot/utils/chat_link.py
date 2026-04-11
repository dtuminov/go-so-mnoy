"""Валидация и нормализация пользовательских ссылок на чат Telegram."""

from __future__ import annotations

import re

_MAX_LEN = 512

# Accept https://t.me/..., http://t.me/..., t.me/... (без схемы — допишем),
# а также tg://...
_TME_PATTERN = re.compile(r"^(?:https?://)?t\.me/\S+$", re.IGNORECASE)
_TG_PATTERN = re.compile(r"^tg://\S+$", re.IGNORECASE)


class InvalidChatLinkError(ValueError):
    """Пользователь прислал строку, которая не похожа на Telegram-ссылку."""


def normalize_chat_link(raw: str) -> str:
    """Приводит ввод к каноничному виду `https://t.me/...` или `tg://...`.

    Бросает `InvalidChatLinkError` — вызывающий код показывает её сообщение.
    """
    s = (raw or "").strip()
    if not s:
        raise InvalidChatLinkError("Пустая ссылка.")
    if len(s) > _MAX_LEN:
        s = s[:_MAX_LEN]

    if _TG_PATTERN.match(s):
        return s

    if _TME_PATTERN.match(s):
        # дописываем схему, если её не было
        if s.lower().startswith("http://"):
            return "https://" + s[len("http://") :]
        if not s.lower().startswith("https://"):
            return "https://" + s
        return s

    raise InvalidChatLinkError(
        "Нужна ссылка Telegram: например, <code>https://t.me/joinchat/…</code> "
        "или <code>https://t.me/username</code>.",
    )
