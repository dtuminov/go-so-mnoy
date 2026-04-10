from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")

    events: Mapped[list["Event"]] = relationship(back_populates="city")
    company_seekings: Mapped[list["CompanySeeking"]] = relationship(
        back_populates="city",
    )
