from datetime import date, datetime, timezone
from html import escape
from zoneinfo import ZoneInfo


MSK = ZoneInfo("Europe/Moscow")

_MONTHS_GEN = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


def format_datetime_msk(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    msk = dt.astimezone(MSK)
    today = datetime.now(MSK).date()
    d = msk.date()
    time_str = msk.strftime("%H:%M")

    if d == today:
        return f"сегодня, {time_str}"
    tomorrow = date(today.year, today.month, today.day)
    from datetime import timedelta
    if d == today + timedelta(days=1):
        return f"завтра, {time_str}"

    month = _MONTHS_GEN[msk.month]
    if d.year == today.year:
        return f"{msk.day} {month}, {time_str}"
    return f"{msk.day} {month} {msk.year}, {time_str}"


def esc(text: str) -> str:
    return escape(text, quote=False)
