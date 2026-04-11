from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo


MSK = ZoneInfo("Europe/Moscow")


def format_datetime_msk(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"


def esc(text: str) -> str:
    return escape(text, quote=False)
