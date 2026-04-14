"""Подсказки мест и организаций через 2GIS API.

Ищет по названиям (рестораны, парки, клубы) и адресам.
Бесплатно до 1000 запросов/день.
"""

from __future__ import annotations

from dataclasses import dataclass

import aiohttp

SEARCH_URL = "https://catalog.api.2gis.com/3.0/items"


def _build_address(addr: dict) -> str:
    """Собирает читаемый адрес из components 2GIS."""
    parts: list[str] = []
    for comp in addr.get("components", []):
        t = comp.get("type", "")
        if t == "street_number":
            street = comp.get("street", "")
            number = comp.get("number", "")
            if street and number:
                parts.append(f"{street}, {number}")
            elif street:
                parts.append(street)
        elif t == "location":
            comment = comp.get("comment", "")
            if comment:
                parts.append(comment)
    return ", ".join(parts)


@dataclass(frozen=True)
class PlaceSuggestion:
    name: str  # короткое название для кнопки
    full: str  # полное «название, адрес» для сохранения


async def suggest_places(
    query: str,
    api_key: str,
    *,
    count: int = 4,
) -> list[PlaceSuggestion]:
    """Ищет места и организации через 2GIS."""
    params = {
        "key": api_key,
        "q": query,
        "page_size": str(count),
        "fields": "items.point,items.address",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                SEARCH_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []

    results: list[PlaceSuggestion] = []
    for item in data.get("result", {}).get("items", []):
        name = item.get("name", "").strip()
        if not name:
            continue

        addr_obj = item.get("address", {}) or {}
        # 2GIS хранит адрес в components
        address = _build_address(addr_obj)

        if address:
            full = f"{name}, {address}"
            btn_name = f"{name} · {address}"
        else:
            full = name
            btn_name = name

        results.append(PlaceSuggestion(name=btn_name[:60], full=full))

    return results[:count]
