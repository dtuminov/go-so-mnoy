"""Подсказки адресов через Dadata Suggestions API."""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp

DADATA_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"


@dataclass(frozen=True)
class AddressSuggestion:
    title: str  # короткое название для кнопки
    full_address: str  # полный адрес для сохранения
    lat: float | None = None
    lon: float | None = None


async def suggest_address(
    query: str,
    api_key: str,
    *,
    city: str | None = None,
    count: int = 5,
) -> list[AddressSuggestion]:
    """Запрашивает подсказки адресов у Dadata.

    `city` — ограничивает поиск конкретным городом (например, "Москва").
    """
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body: dict = {
        "query": query,
        "count": count,
        "from_bound": {"value": "street"},
        "to_bound": {"value": "house"},
    }
    if city:
        body["locations"] = [{"city": city}]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DADATA_URL,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []

    results: list[AddressSuggestion] = []
    for item in data.get("suggestions", []):
        value = item.get("value", "").strip()
        if not value:
            continue
        d = item.get("data", {}) or {}
        lat = _safe_float(d.get("geo_lat"))
        lon = _safe_float(d.get("geo_lon"))
        # Короткое название: убираем город из начала если он совпадает
        title = value
        if city and title.lower().startswith(f"г {city.lower()},"):
            title = title[len(f"г {city},"):].strip()
        results.append(AddressSuggestion(
            title=title,
            full_address=value,
            lat=lat,
            lon=lon,
        ))
    return results


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
