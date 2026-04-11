from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text(), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    place_text: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="draft")
    published_notified: Mapped[bool] = mapped_column(default=False, server_default="false")
    reminder_sent: Mapped[bool] = mapped_column(default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    city: Mapped["City"] = relationship(back_populates="events")
    organizer: Mapped["User"] = relationship(
        back_populates="organized_events",
        foreign_keys=[organizer_id],
    )
    participants: Mapped[list["EventParticipant"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
