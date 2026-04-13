"""Reverse geocoding через Nominatim (OpenStreetMap) — город по координатам."""

from __future__ import annotations

import aiohttp


async def city_name_by_coords(lat: float, lon: float) -> str | None:
    """Возвращает название города по координатам или None."""
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": str(lat),
        "lon": str(lon),
        "format": "jsonv2",
        "accept-language": "ru",
        "zoom": 10,
    }
    headers = {"User-Agent": "go-so-mnoy-bot/1.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception:
        return None

    addr = data.get("address", {})
    return addr.get("city") or addr.get("town") or addr.get("village") or None
