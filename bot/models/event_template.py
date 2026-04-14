from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class EventTemplate(Base):
    """Шаблон события для deep link из канала.

    Админ создаёт шаблон (название + место), получает ссылку
    `t.me/bot?start=tpl_<id>`. Юзер нажимает → создаёт событие
    с предзаполненными полями.
    """

    __tablename__ = "event_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    place_text: Mapped[str] = mapped_column(String(512), default="", server_default="")
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    cover_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
