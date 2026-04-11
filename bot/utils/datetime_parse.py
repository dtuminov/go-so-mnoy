from datetime import datetime

from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def parse_user_datetime_msk(text: str) -> datetime:
    """Разбор даты/времени ввода пользователя в зоне Москвы."""
    raw = text.strip()
    errors: list[str] = []
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(raw, fmt)
            return naive.replace(tzinfo=MSK)
        except ValueError as e:
            errors.append(str(e))
            continue
    raise ValueError(
        "Не получилось разобрать дату. Примеры: 25.04.2026 19:00 или 2026-04-25 19:00",
    ) from None
