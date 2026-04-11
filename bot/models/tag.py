from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


from bot.db.base import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    emoji: Mapped[str] = mapped_column(String(8), default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="true")

    def label(self) -> str:
        """Короткая строка «эмодзи название», удобно печатать в карточке."""
        return f"{self.emoji} {self.name}".strip()
