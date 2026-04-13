"""Парсинг ссылок на Яндекс Карты и 2GIS для извлечения названия места."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import aiohttp


async def resolve_short_url(url: str, timeout: float = 5) -> str | None:
    """Раскрывает короткую ссылку (redirect) и возвращает финальный URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                return str(resp.url)
    except Exception:
        return None


def _extract_from_yandex_url(url: str) -> str | None:
    """Извлекает название места из полного URL Яндекс Карт."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    # ?text=Парк+Горького
    if "text" in qs:
        return unquote(qs["text"][0]).strip() or None

    # /maps/org/название/id/ — название в пути
    org_match = re.search(r"/org/([^/]+)/", parsed.path)
    if org_match:
        return unquote(org_match.group(1)).replace("_", " ").strip() or None

    # /maps/адрес/ — последний сегмент пути
    path_parts = [p for p in parsed.path.split("/") if p and p != "maps"]
    if path_parts:
        candidate = unquote(path_parts[-1]).replace("_", " ").replace("+", " ")
        # Фильтруем hash-подобные строки
        if len(candidate) > 3 and not candidate.startswith("-"):
            return candidate.strip()

    return None


_YANDEX_MAPS_RE = re.compile(
    r"https?://(?:yandex\.ru/maps|maps\.yandex\.ru|yandex\.com/maps)",
)

_SHORT_YANDEX_RE = re.compile(
    r"https?://yandex\.ru/maps/-/[A-Za-z0-9~_]+",
)


async def extract_place_from_url(text: str) -> str | None:
    """Пытается извлечь название места из текста, если в нём есть ссылка на карты.

    Возвращает название или None если не удалось.
    """
    text = text.strip()

    # Короткая ссылка: yandex.ru/maps/-/CDa5e4~2
    short_match = _SHORT_YANDEX_RE.search(text)
    if short_match:
        full_url = await resolve_short_url(short_match.group(0))
        if full_url:
            return _extract_from_yandex_url(full_url)
        return None

    # Полная ссылка Яндекс Карт
    if _YANDEX_MAPS_RE.search(text):
        return _extract_from_yandex_url(text)

    return None


def is_maps_url(text: str) -> bool:
    """Проверяет, содержит ли текст ссылку на карты."""
    text = text.strip()
    return bool(_YANDEX_MAPS_RE.search(text) or _SHORT_YANDEX_RE.search(text))
